# Payment Ledger (P1) Implementation Plan

## Overview

Introduce a `payments` table holding individual payment events linked to `payment_instances`. A "mark as paid" action becomes "record a payment" with amount, date, and optional note; several payments — including partial ones — can be recorded against one instance. `PaymentInstance.status/paid_at/paid_amount` become a denormalized summary recomputed from the ledger, keeping reminders, xlsx export, monthly summary, JSON restore and the API backward compatible.

## Desired End State

- Every paid instance has ≥1 `payments` row; existing paid instances are backfilled with one row.
- `POST /bills/payments/{id}/payments` records a payment; partial payments leave the instance `upcoming`/`overdue` with `paid_amount` set to the running total.
- Instance becomes `paid` only when the ledger total ≥ instance amount; the next recurring instance is generated at that transition.
- Payments page: mark-paid dialog has amount (default = remaining balance), date (default today), note; rows show paid-so-far and a payment history with delete-per-event; revert clears all events.
- JSON backup round-trips the ledger (schema_version 4); v2/v3 backups/snapshots synthesize one payment per paid instance.

## Frozen API Contract

All paths are under the existing `bills` router (prefix `/bills`).

### New: `POST /bills/payments/{instance_id}/payments`

Request `PaymentCreate`:
```json
{ "amount": "120.00", "paid_on": "2026-09-20", "note": "optional" }
```
- `amount: Decimal`, must be `> 0` (422 otherwise).
- `paid_on: date | null` — null means "today" (server UTC date). Dates more than one day after the server date are rejected with 422 (one day of slack so users ahead of UTC can record their local today).
- `note: str | null`.

Response: full updated `PaymentInstanceOut` (see below), 200.

Behavior:
1. Load instance scoped to `current_user` (via `bill_id → BillTemplate.user_id`), 404 if missing, 403/404 cross-user.
2. Append `Payment(amount, paid_on, note)`, recompute summary.
3. If instance **transitioned** from not-fully-paid to fully-paid and template is not paused → `generate_next_instance` (idempotent; same call as today's mark-paid).
4. Single commit.

### New: `DELETE /bills/payments/{instance_id}/payments/{payment_id}`

Response: full updated `PaymentInstanceOut`, 200. 404 if the payment does not belong to the instance. Deletes the event, recomputes summary (an instance can go from `paid` back to `overdue`/`upcoming`). Does **not** delete an auto-generated next instance (consistent with existing revert behavior).

### Existing: `POST /bills/payments/{instance_id}/pay` (kept, reimplemented)

Request unchanged: `MarkPaidRequest { paid_amount: Decimal | null, notes: str | null }`.
- Creates exactly **one** payment event with `amount = paid_amount if paid_amount is not None else remaining_balance` where `remaining_balance = max(instance.amount - current_total, 0)`; `paid_on = today`; `note = notes`.
- If the instance is **already fully paid**, return it unchanged (idempotent; prevents duplicate events from retries/double-clicks).
- If `remaining_balance == 0` but instance is not fully paid (impossible unless amount column changed) → treat as already paid.
- If `paid_amount` is explicitly less than `remaining_balance`, the instance stays partially paid (new semantics; document in docstring).
- Recurrence on transition as above.

### Existing: `POST /bills/payments/{instance_id}/unpay`

Now deletes **all** payment events for the instance and recomputes the summary. Response unchanged (`PaymentInstanceOut`). 400 if instance is not `paid` (keep the existing guard). Route name and payload unchanged.

### Response: `PaymentInstanceOut` gains `payments`

```json
{
  "id": 1, "bill_id": 2, "period": "2026-09", "due_date": "...", "amount": "120.00",
  "status": "paid", "paid_at": "...", "paid_amount": "120.00", "notes": null,
  "bill_name": "...", "currency": "PLN", "frequency": "monthly", "category": "utilities",
  "email_sent_at": null,
  "payments": [
    { "id": 9, "instance_id": 1, "amount": "70.00", "paid_on": "2026-09-18",
      "note": "part 1", "created_at": "..." }
  ]
}
```
`GET /bills/payments?month=` must eager-load payments (no N+1).

## Data Model

New `backend/app/models/payment.py`:

```python
class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("payment_instances.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    instance: Mapped["PaymentInstance"] = relationship(back_populates="payments")
```

`PaymentInstance` gains:
```python
payments: Mapped[list["Payment"]] = relationship(
    back_populates="instance", cascade="all, delete-orphan",
    order_by="Payment.paid_on, Payment.id",
)
```
Import the new model in `tests/conftest.py` and `alembic/env.py` alongside the others.

## Summary Derivation (service)

New `backend/app/services/payments.py` — all ledger business logic lives here (routers stay thin):

- `get_total(instance) -> Decimal` — `sum(p.amount for p in instance.payments)`.
- `recalculate_instance(instance, *, today=None) -> None`:
  - `total == 0` → `paid_amount=None`, `paid_at=None`, `status = overdue if due_date < today else upcoming`.
  - `0 < total < amount` → keeping `upcoming`/`overdue` by due date; `paid_amount=total`; `paid_at=None`.
  - `total >= amount` → `status=paid`; `paid_amount=total`; `paid_at = max(p.created_at for p in payments)`.
  - `today` param exists for testability; default `date.today()`.
- `record_payment(db, instance, *, amount, paid_on, note) -> tuple[Payment, bool]` — appends and returns `(payment, became_fully_paid)` where `became_fully_paid = previous_status != paid and new_status == paid`.
- `delete_payment(db, instance, payment_id) -> bool`.
- `clear_payments(db, instance) -> int`.

Invariant: `paid_amount` equals the ledger total whenever any payment exists; `paid_at` is non-null **iff** status is `paid`.

## Migration

Hand-written (per lessons.md), `alembic/versions/<rev>_add_payments_ledger.py`, `down_revision = "e1f2a3b4c5d6"`.

- `op.create_table("payments", ...)` with columns above; `created_at` `server_default=sa.text("now()")`.
- `op.create_index("ix_payments_instance_id", "payments", ["instance_id"])`.
- Backfill:
```sql
INSERT INTO payments (instance_id, amount, paid_on, note, created_at)
SELECT id, COALESCE(paid_amount, amount), COALESCE(paid_at::date, due_date), notes,
       COALESCE(paid_at, created_at)
FROM payment_instances
WHERE status = 'paid'
```
- Downgrade drops index + table.

## Backup / Restore (schema_version 4)

- `app/schemas/bill.py`:
  - `BackupPayment`: `id: int`, `instance_id: int`, `amount: Decimal`, `paid_on: str`, `note: str | None`, `created_at: str`.
  - `BackupPayload.payments: list[BackupPayment] = []` (default keeps v2/v3 payloads and existing snapshots parseable).
- `GET /export/json` → `schema_version: 4`; include payments for exported (non-deleted) instances. Keep emitting instance fields unchanged.
- `POST /export/restore` accepts `{2, 3, 4}`.
  - `_apply_backup`: delete payments before instances (explicit `DELETE ... WHERE instance_id IN (...)` or rely on cascade), insert payments after instances using the instance id map.
  - For v2/v3 payloads (`payments` empty): synthesize one payment per `status == paid` instance, `amount = paid_amount or amount`, `paid_on = date(paid_at) or due_date`, `note = instance.notes`.
  - Old `restore_snapshots` rows (schema_version 3) must keep restoring via the same synthesis.
- Do **not** change xlsx or `GET /export/summary`.

## Reminders / Monthly Summary

No logic changes. Notes: partial payments still receive reminders (`status != paid`); the monthly summary treats partial instances as unpaid with the expected amount. This is accepted for P1.

## Frontend

### `src/lib/payments-api.ts`
- Add `PaymentEvent { id, instance_id, amount, paid_on, note, created_at }` and `payments: PaymentEvent[]` on `PaymentInstanceOut`.
- Add `addPayment(instanceId, amount: number, paidOn: string | null, note?: string): Promise<PaymentInstanceOut>` → POST `/bills/payments/{id}/payments`.
- Add `deletePaymentEvent(instanceId, paymentId): Promise<PaymentInstanceOut>` → DELETE `/bills/payments/{id}/payments/{paymentId}`.
- Keep `markPaid`/`revertPay` (revert now clears all events).

### `MarkPaidDialog` → record payment
- Fields: amount (default **remaining** = `amount - paid_amount`, min 0.01), date `<input type="date">` default today local, note (existing).
- Submits `addPayment`; on success parent replaces instance.
- Keep dialog title key and `confirm` label (tests click `Mark as Paid`), add new keys for date/remaining/partial.
- Show inline error on failure (existing pattern).

### `PaymentRow`
- When `payments.length > 0`: show paid-so-far summary (`paid {paid_amount} of {amount}` and, if not fully paid, `remaining {remaining}`); list each event (date, amount, note) with a delete button (`aria-label` e.g. `Delete payment record`).
- Keep the `Revert payment` button for fully-paid rows (calls `revertPay` → clears all); it must remain reachable for e2e test 03.
- Replace the old notes popover source with ledger notes when history exists; keep legacy `instance.notes` display only if no ledger rows (backfilled data always has rows, so effectively ledger-driven).

### i18n
Add keys to `messages/en.json`, `pl.json`, `de.json` under `PaymentsPage`/`PaymentRow`/`MarkPaidDialog` (existing section names). No missing keys — next-intl throws at runtime.

## Tests

Backend — new `tests/test_payments_ledger.py`:
- full payment via `POST .../payments` → `status=paid`, `paid_amount=amount`, `paid_at` set, one `payments` entry, next instance generated.
- partial then completing payment → first leaves `overdue`/`upcoming` with `paid_amount=partial` and **no** next instance; second sets `paid` and generates next; two entries ordered.
- overpayment keeps `paid` and `paid_amount = total`.
- delete one event recomputes (paid → partial/overdue); delete last event clears fields.
- `POST .../unpay` clears all events.
- amount `<= 0` → 422; future `paid_on` → 422.
- cross-user access → 403 (match existing scoping style in `test_user_scoping.py`).
- legacy `/pay` default records the remaining balance and is idempotent when already paid.
Update `tests/test_restore.py`: v4 round-trip includes ledger rows; v3 backup synthesizes payments; keep existing assertions passing. Update `tests/test_user_scoping.py` only if response shape changes break it (payments list added is additive).

Frontend e2e — update `tests/e2e/03-mark-payment-paid.spec.ts` for the new dialog (fill date/amount if needed), assert the payment history entry appears; keep existing assertions (revert button visible, mark button gone). Add a partial-payment case: pay half, assert status stays overdue/upcoming and remaining shown, then complete it.

## Verification Commands

Backend (no Postgres locally; pytest is CI-only):
```
cd backend && nix shell nixpkgs#python313 -c bash -c 'export UV_PYTHON=python3.13; nix run nixpkgs#uv -- run black --check --target-version py313 .; nix run nixpkgs#uv -- run mypy app'
```
Frontend:
```
cd frontend && nix shell nixpkgs#nodejs_22 -c bash -c 'npm run lint; npm run build'
```

## What We're NOT Doing

- No payment editing (delete + re-add instead).
- No payment method/reference fields.
- No changes to xlsx columns, monthly summary, or reminder logic.
- No removal of the denormalized instance columns (they stay as the compatibility summary).
- No per-payment soft delete (events are hard-deleted; instance tombstones remain for instances only).
