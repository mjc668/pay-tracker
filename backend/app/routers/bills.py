from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import current_user
from app.models.bill import BillTemplate, PaymentInstance, PaymentStatus
from app.models.user import User
from app.schemas.bill import (
    BillTemplateCreate,
    BillTemplateOut,
    BillTemplateUpdate,
    HasDeletedFutureOut,
    MarkPaidRequest,
    PaymentCreate,
    PaymentInstanceOut,
)
from app.services.payments import (
    clear_payments,
    delete_payment as delete_payment_record,
    get_total,
    record_payment,
)
from app.services.recurrence import (
    _due_date_for_period,
    backfill_template_instances,
    ensure_current_period_instances,
    generate_next_instance,
)

router = APIRouter(prefix="/bills", tags=["bills"])


def _get_scoped_instance(db: Session, instance_id: int, me: User) -> PaymentInstance:
    """Load an instance and enforce ownership through bill → template.user_id."""
    instance = db.get(PaymentInstance, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Payment instance not found")
    if instance.template.user_id != me.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return instance


def _to_out(
    inst: PaymentInstance,
    *,
    override_status: PaymentStatus | None = None,
) -> PaymentInstanceOut:
    return PaymentInstanceOut.model_validate(
        {
            "id": inst.id,
            "bill_id": inst.bill_id,
            "period": inst.period,
            "due_date": inst.due_date,
            "amount": inst.amount,
            "status": override_status if override_status is not None else inst.status,
            "paid_at": inst.paid_at,
            "paid_amount": inst.paid_amount,
            "notes": inst.notes,
            "bill_name": inst.template.name,
            "currency": inst.template.currency,
            "frequency": inst.template.frequency,
            "category": inst.template.category,
            "email_sent_at": inst.email_sent_at,
            # Match the relationship's order_by even if the in-memory
            # collection was appended to before a reload.
            "payments": sorted(inst.payments, key=lambda p: (p.paid_on, p.id)),
        }
    )


@router.get("", response_model=list[BillTemplateOut])
def list_bills(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    q = db.query(BillTemplate).filter(BillTemplate.user_id == me.id)
    if not include_archived:
        q = q.filter(BillTemplate.is_archived.is_(False))
    return q.order_by(BillTemplate.name).all()


@router.post("", response_model=BillTemplateOut, status_code=status.HTTP_201_CREATED)
def create_bill(
    body: BillTemplateCreate,
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    from app.models.bill import BillFrequency as BF

    RECURRING = (BF.monthly, BF.every_2_months, BF.quarterly)

    now = datetime.now(timezone.utc)
    if body.due_month and body.frequency in (BF.annual, BF.one_off):
        year = now.year if body.due_month >= now.month else now.year + 1
        start_period = f"{year:04d}-{body.due_month:02d}"
    elif body.due_month and body.frequency in RECURRING:
        start_period = f"{now.year:04d}-{body.due_month:02d}"
    else:
        start_period = now.strftime("%Y-%m")
    data = body.model_dump(exclude={"due_month"})
    bill = BillTemplate(**data, user_id=me.id, start_period=start_period)
    db.add(bill)
    db.commit()
    db.refresh(bill)

    current_period = now.strftime("%Y-%m")
    if body.frequency in RECURRING and start_period < current_period:
        backfill_template_instances(db, bill, start_period, current_period)

    return bill


# Literal-path routes declared before parameterized /{bill_id} routes to prevent
# FastAPI from matching "payments" as an integer bill_id.
@router.get("/payments", response_model=list[PaymentInstanceOut])
def list_payments(
    month: str | None = None,  # "YYYY-MM"
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    today = date.today()
    current_month = today.strftime("%Y-%m")
    if month is None:
        month = current_month

    # NOTE: instance seeding was intentionally moved to POST /bills/sync-instances
    # so that GET list_payments remains side-effect free.

    instances = (
        db.query(PaymentInstance)
        .options(
            selectinload(PaymentInstance.template),
            selectinload(PaymentInstance.payments),
        )
        .join(BillTemplate, PaymentInstance.bill_id == BillTemplate.id)
        .filter(
            BillTemplate.user_id == me.id,
            PaymentInstance.period == month,
            PaymentInstance.is_deleted.is_(False),
        )
        .order_by(PaymentInstance.due_date)
        .all()
    )

    result = []
    for inst in instances:
        # Dynamic overdue: override status in response without writing to DB
        override = (
            PaymentStatus.overdue
            if inst.status == PaymentStatus.upcoming and inst.due_date < today
            else None
        )
        result.append(_to_out(inst, override_status=override))
    return result


@router.post("/payments/{instance_id}/payments", response_model=PaymentInstanceOut)
def add_payment(
    instance_id: int,
    body: PaymentCreate,
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    """Record a partial or full payment event against an instance."""
    instance = _get_scoped_instance(db, instance_id, me)
    template = instance.template

    _, became_fully_paid = record_payment(
        db,
        instance,
        amount=body.amount,
        paid_on=body.paid_on or date.today(),
        note=body.note,
    )
    period = instance.period
    db.commit()

    # auto-create next period instance only on the transition to fully paid
    if became_fully_paid and not template.is_paused:
        generate_next_instance(db, template, period)

    db.refresh(instance)
    return _to_out(instance)


@router.delete(
    "/payments/{instance_id}/payments/{payment_id}",
    response_model=PaymentInstanceOut,
)
def delete_payment_event(
    instance_id: int,
    payment_id: int,
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    """Delete a single payment event and recompute the instance summary."""
    instance = _get_scoped_instance(db, instance_id, me)

    deleted = delete_payment_record(db, instance, payment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Payment not found")

    db.commit()
    db.refresh(instance)
    return _to_out(instance)


@router.post("/payments/{instance_id}/pay", response_model=PaymentInstanceOut)
def mark_paid(
    instance_id: int,
    body: MarkPaidRequest,
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    """Legacy mark-as-paid: record one event for the remaining balance.

    `paid_amount` defaults to `max(amount - ledger_total, 0)`. An explicit
    lower amount leaves the instance partially paid. Calling this on an
    already fully-paid instance is a no-op (prevents duplicate events from
    retries/double-clicks).
    """
    instance = _get_scoped_instance(db, instance_id, me)
    template = instance.template

    if instance.status == PaymentStatus.paid:
        return _to_out(instance)

    total = get_total(instance)
    remaining = max(instance.amount - total, Decimal("0"))
    if remaining == 0:
        # Ledger already covers the amount but the summary is stale (only
        # possible if the instance amount changed): treat as already paid.
        return _to_out(instance)

    amount = body.paid_amount if body.paid_amount is not None else remaining
    _, became_fully_paid = record_payment(
        db,
        instance,
        amount=amount,
        paid_on=date.today(),
        note=body.notes,
    )
    period = instance.period
    db.commit()

    # auto-create next period instance only on the transition to fully paid
    if became_fully_paid and not template.is_paused:
        generate_next_instance(db, template, period)

    db.refresh(instance)
    return _to_out(instance)


@router.post("/payments/{instance_id}/unpay", response_model=PaymentInstanceOut)
def revert_payment(
    instance_id: int,
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    """Revert a fully-paid instance by clearing every payment event."""
    instance = _get_scoped_instance(db, instance_id, me)
    if instance.status != PaymentStatus.paid:
        raise HTTPException(status_code=400, detail="Payment is not marked as paid")

    clear_payments(db, instance)
    db.commit()
    db.refresh(instance)
    return _to_out(instance)


@router.delete("/payments/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_payment(
    instance_id: int,
    delete_future: bool = Query(False),
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    instance = db.get(PaymentInstance, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Payment instance not found")

    template = instance.template
    if template.user_id != me.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    instance.is_deleted = True

    if delete_future:
        db.query(PaymentInstance).filter(
            PaymentInstance.bill_id == instance.bill_id,
            PaymentInstance.due_date > instance.due_date,
            PaymentInstance.status != PaymentStatus.paid,
            PaymentInstance.is_deleted.is_(False),
        ).update({"is_deleted": True}, synchronize_session=False)

    db.commit()


@router.post("/sync-instances", status_code=status.HTTP_204_NO_CONTENT)
def sync_instances(
    month: str | None = None,
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    """Explicitly seed payment instances for the given month (or current month).
    Replaces the previous seed-on-read side effect in list_payments."""
    today = date.today()
    current_month = today.strftime("%Y-%m")
    target = month or current_month
    if target >= current_month:
        ensure_current_period_instances(db, target, me.id)


@router.get("/{bill_id}/has-deleted-future", response_model=HasDeletedFutureOut)
def has_deleted_future(
    bill_id: int,
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    bill = db.get(BillTemplate, bill_id)
    if not bill or bill.user_id != me.id:
        raise HTTPException(status_code=404, detail="Bill not found")
    current_period = date.today().strftime("%Y-%m")
    exists = (
        db.query(PaymentInstance)
        .filter(
            PaymentInstance.bill_id == bill_id,
            PaymentInstance.is_deleted.is_(True),
            PaymentInstance.period >= current_period,
        )
        .first()
        is not None
    )
    return HasDeletedFutureOut(has_deleted_future=exists)


@router.patch("/{bill_id}", response_model=BillTemplateOut)
def update_bill(
    bill_id: int,
    body: BillTemplateUpdate,
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    bill = db.get(BillTemplate, bill_id)
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.user_id != me.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    from app.models.bill import BillFrequency as BF

    updates = body.model_dump(exclude_unset=True)
    updates.pop("recreate_deleted_future", None)
    due_month = updates.pop("due_month", None)
    due_day_changed = "due_day" in updates and updates["due_day"] != bill.due_day
    for field, value in updates.items():
        setattr(bill, field, value)

    # Recalculate start_period when due_month changes for annual/one_off
    effective_frequency = updates.get("frequency", bill.frequency)
    if due_month is not None and effective_frequency in (BF.annual, BF.one_off):
        now = datetime.now(timezone.utc)
        year = now.year if due_month >= now.month else now.year + 1
        bill.start_period = f"{year:04d}-{due_month:02d}"

    if due_day_changed:
        unpaid = (
            db.query(PaymentInstance)
            .filter(
                PaymentInstance.bill_id == bill.id,
                PaymentInstance.status != PaymentStatus.paid,
                PaymentInstance.is_deleted.is_(False),
            )
            .all()
        )
        for inst in unpaid:
            inst.due_date = _due_date_for_period(inst.period, bill.due_day)

    if body.recreate_deleted_future:
        current_period = date.today().strftime("%Y-%m")
        tombstones = (
            db.query(PaymentInstance)
            .filter(
                PaymentInstance.bill_id == bill.id,
                PaymentInstance.is_deleted.is_(True),
                PaymentInstance.period >= current_period,
            )
            .all()
        )
        for inst in tombstones:
            inst.is_deleted = False
            inst.amount = bill.amount
            inst.due_date = _due_date_for_period(inst.period, bill.due_day)
            inst.status = PaymentStatus.upcoming

    db.commit()
    db.refresh(bill)
    return bill


@router.post("/{bill_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
def archive_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    bill = db.get(BillTemplate, bill_id)
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.user_id != me.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    bill.is_archived = True
    db.commit()
