# Limited Occurrences Implementation Plan

## Frozen contract

- New nullable `BillTemplate.max_occurrences: int` (1–999; null = unlimited).
- **Semantics:** the cap counts occurrences from the first scheduled occurrence (the anchor), inclusive. Monthly starting this month with cap 4 → this month, +1, +2, +3 — no fifth.
- `one_off` bills ignore it (forced null). `interval_count` is unaffected.
- Every generation path respects the cap: current-period seeding, backfill, next-instance-after-payment, series generator. The dashboard forecast (`_occurrences_in_period`) also respects it.
- **Editing down:** on update, future (due_date ≥ today) unpaid, non-deleted instances with **no payment events** whose occurrence index ≥ cap are removed; paid or partially-paid history is never touched.
- Backup schema **version 7**; `BackupTemplate.max_occurrences: int | None = None`; restore accepts 2–7.

## Backend

1. `app/models/bill.py`: `max_occurrences: Mapped[int | None] = mapped_column(Integer)`.
2. Migration `alembic/versions/a7b8c9d0e1f2_limited_occurrences.py`, `down_revision = "f6a7b8c9d0e1"`: nullable Integer column, no server_default (per lessons.md); downgrade drops it.
3. `app/services/recurrence.py`:
   - `_occurrence_index(template, due_date) -> int`: weekly → `(due - start_date).days // (7*interval)`; month-anchored → `months_diff // step_months` from the anchor; one_off → 0.
   - `_occurrences_in_period`: filter out every date whose index ≥ `max_occurrences` (single place → seeding, backfill, series, forecast all get it for free).
   - `generate_next_instance`: after computing the next due date, return `None` when its index ≥ the cap.
   - `prune_occurrences_beyond_cap(db, template, today) -> int`: deletes future unpaid, non-deleted instances with zero payments whose index ≥ cap (used by update).
4. `app/schemas/bill.py`: `max_occurrences: int | None = Field(None, ge=1, le=999)` on Create/Update/Out; `BackupTemplate.max_occurrences: int | None = None`.
5. `app/routers/bills.py`:
   - create: persist (force null for one_off); update: persist, then run the prune when the effective cap shrank.
   - `_to_out` passes the field through (ORM-backed).
6. `app/routers/export.py`: schema_version 7 export + restore accepts {2..7}.
7. Tests:
   - recurrence: occurrence index per unit; `_occurrences_in_period` cap for monthly/weekly; `generate_next_instance` returns None at the cap; seeding/backfill stop at the cap.
   - create/update: bounds 422; one_off coerced to null; lowering the cap prunes future unpaid rows but keeps paid/partially-paid ones.
   - series generator respects the cap.
   - stats: forecast does not count occurrences past the cap.
   - restore: v7 round-trip; v6 payload restores with null.

## Frontend

1. `src/lib/bills-api.ts`: `max_occurrences: number | null` on Out/Create/Update.
2. `src/components/bills/BillTemplateForm.tsx`: under the interval row (hidden for one-off), a checkbox **"Set number of payments"**; when checked, a number input (min 1, max 999, default 12) labelled **"Number of payments"**. Payload: `max_occurrences: limited ? parsed : null`; client validation for an empty/invalid count.
3. `src/components/bills/BillTemplateRow.tsx` (+ archived page, `DeletePaymentDialog`): append a muted `· {count} payments` when set.
4. i18n keys in `BillTemplateForm` / `BillTemplateRow` / `Frequencies` sections, en/pl/de parity.
5. e2e `tests/e2e/14-limited-occurrences.spec.ts`: create a monthly bill with 4 payments via the UI; generate 6 months in the dialog; assert the bill appears in the current month, in month +3, and **not** in month +4. Keep dates relative (`Date`-derived).

## Verification

```
cd backend && nix shell nixpkgs#python313 -c bash -c 'export UV_PYTHON=python3.13; nix run nixpkgs#uv -- run black --check --target-version py313 .; nix run nixpkgs#uv -- run mypy app'
cd frontend && nix shell nixpkgs#nodejs_22 -c bash -c 'npm run lint; npm run build'
```

## Out of scope

- End-date based limits (only a count).
- Changing `interval_count` semantics.
- Re-enabling generation after a cap is removed beyond the normal seeding rules (it resumes naturally).
