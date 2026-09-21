# Recurrence Flexibility (weekly + intervals) Implementation Plan

## Frozen contract

- `BillFrequency = weekly | monthly | annual | one_off` (enum members removed: `every_2_months`, `quarterly`).
- `BillTemplate.interval_count: int` NOT NULL default 1. Bounds: weekly 1–4, monthly 1–12, annual 1–5, one_off forced 1.
- `BillTemplate.start_date: date | None` — weekly anchor; null for other units.
- Idempotency key: **unique `(bill_id, due_date)`** replaces unique `(bill_id, period)`. `period` remains `"YYYY-MM"` derived from `due_date`.
- Create/Update/Out schemas gain `interval_count: int = 1` and `start_date: date | None = None`.
  - Weekly requires `start_date` (422 if missing). `start_date` may be in the past (backfill); occurrences run from `start_date` through the end of the current month.
  - For non-weekly units `start_date` is ignored and stored as null; `due_day` is ignored and stored as null for weekly.
  - Interval bounds validated against the effective frequency after create/update merge → 422.
  - Legacy frequency strings are rejected on new writes (422).
- Backup `schema_version: 5`; export includes `interval_count` + `start_date`; restore accepts 2–5 and maps `every_2_months` → monthly/2, `quarterly` → monthly/3 when `interval_count` is absent.

## Backend

### Model + migration
- `app/models/bill.py`: enum per contract; `interval_count` + `start_date` columns; `PaymentInstance.__table_args__` → `UniqueConstraint("bill_id", "due_date", name="uq_payment_instance_bill_due_date")`.
- Hand-written migration `alembic/versions/e5f6a7b8c9d0_recurrence_intervals.py`, `down_revision = "d4e5f6a7b8c9"`:
  1. `add_column interval_count INTEGER NOT NULL server_default="1"` then `alter_column(server_default=None)`.
  2. `add_column start_date DATE NULL`.
  3. `UPDATE bill_templates SET interval_count=2 WHERE frequency='every_2_months'`; `=3 WHERE frequency='quarterly'`; then `frequency='monthly'` for both.
  4. `drop_constraint("uq_payment_instance_bill_period", "payment_instances", type_="unique")`; `create_unique_constraint("uq_payment_instance_bill_due_date", "payment_instances", ["bill_id", "due_date"])`.
  - Downgrade: reverse mapping (interval 2 → every_2_months, 3 → quarterly, else monthly/1), drop new constraint, restore old, drop columns.
- Update the `AGENTS.md` hard rule: idempotency key is `(bill_id, due_date)`.

### Recurrence engine (`app/services/recurrence.py`)
- `_next_period(period, frequency, interval) -> str` for month-anchored units only (monthly +interval months; annual +12*interval months).
- `_step_weeks(start: date, interval: int, k: int) -> date` helper (`start + 7*interval*k` days).
- `_bill_active_in_period(template, period) -> bool` for month-anchored units: anchor = `start_period` or `created_at` month; active iff `months_diff % step_months == 0` (`step_months = interval` monthly, `12*interval` annual). Weekly → False (handled by occurrences).
- `_occurrences_in_period(template, period) -> list[date]`:
  - weekly: every `start_date + 7*interval*k` inside that month.
  - month-anchored: `[_due_date_for_period(period, due_day)]` when active, else `[]`.
- `backfill_template_instances(db, template, from_period, to_period) -> int`: iterate periods, create one instance per occurrence; existence check and inserts keyed on `(bill_id, due_date)` (soft-deleted tombstones still block).
- `ensure_current_period_instances(db, period, user_id)`: same occurrence-based creation, existence by `(bill_id, due_date)` ignoring `is_deleted`.
- `generate_next_instance(db, template, paid_due_date: date) -> PaymentInstance | None`: one_off → None; weekly → `paid_due_date + 7*interval`; month-anchored → next period + due date. Idempotent check + `IntegrityError` fallback on `(bill_id, due_date)`. Update callers in `routers/bills.py` (pass `instance.due_date`).
- `generate_future_instances` unchanged in shape (months ahead), now creates all occurrences per month.
- `eligible_for_generation` unchanged (`frequency != one_off`).

### Routers (`app/routers/bills.py`)
- `create_bill`:
  - weekly: `start_period = start_date.strftime("%Y-%m")`; backfill occurrences from `start_period` through the current month.
  - monthly/annual with `due_month`: keep existing year routing (annual/one_off next-year rule; monthly backfill when in the past) with `interval_count` persisted.
  - one_off: unchanged.
  - Persist `interval_count`; `start_date` only for weekly; `due_day` null for weekly.
- `update_bill`:
  - Validate effective `(frequency, interval_count)` bounds.
  - Month-anchored: keep existing `due_date` recompute for unpaid non-deleted instances; start_period recompute for annual/one_off when `due_month` supplied.
  - Weekly schedule change (frequency/interval/start_date changed): recompute `due_date`/`period` for future unpaid non-deleted instances in order — first occurrence on/after today = `start_date + ceil((today - start_date)/step)*step` (or `start_date` if future), then `+k*step`; paid and deleted rows untouched. Clear `start_date`/`due_day` appropriately when switching units.
- `_to_out` unchanged except new fields flow through `BillTemplateOut`/`PaymentInstanceOut`.

### Stats (`app/services/stats.py`)
- `_forecast` uses `len(_occurrences_in_period(template, period)) * template.amount` instead of the boolean active check (weekly months can have multiple occurrences).
- Everything else unchanged (summary/trend/category sum instance rows per period).

### Backup / restore (`app/routers/export.py`, `app/schemas/bill.py`)
- `BackupTemplate`: `frequency: BillFrequency` + `interval_count: int = 1` + `start_date: str | None = None`; a `model_validator(mode="before")` maps legacy `every_2_months`/`quarterly` to `monthly` + interval (only when `interval_count` absent).
- Export: `schema_version: 5`, write `interval_count` and `start_date` (ISO or null).
- Restore: accept `{2, 3, 4, 5}`; `_apply_backup` persists `interval_count`/`start_date`; snapshot restore uses the same `BackupPayload` path (normalization applies).
- No other backup fields change.

## Frontend

- `src/lib/bills-api.ts`: `BillFrequency = "weekly" | "monthly" | "annual" | "one_off"`; add `interval_count: number` and `start_date: string | null` to create/update/out types (payments-api re-export follows).
- `BillTemplateForm.tsx`:
  - Unit pills: Weekly / Monthly / Yearly / One-off.
  - Interval dropdown next to the pills: weeks 1–4, months 1–12, years 1–5; hidden for one-off.
  - Weekly: native `<input type="date">` "First payment date" (required, default today), MonthDayCalendar hidden.
  - Monthly/Yearly: keep MonthDayCalendar; payload sends `interval_count` (1 for one-off) and `start_date` (ISO for weekly, null otherwise).
  - Client validation: weekly needs a first payment date.
- `BillTemplateRow.tsx` + `archived/page.tsx` + `DeletePaymentDialog.tsx`: labels via ICU plurals — e.g. `frequencyWeekly: "Every {count, plural, one {week} other {# weeks}}"`, `frequencyMonthly`, `frequencyAnnual`, `frequencyOneOff`; due label for weekly shows the start date ("Starts {date}") or the weekday; monthly/annual unchanged.
- `GenerateInstancesDialog.tsx`: eligible filter stays `frequency !== "one_off"`.
- i18n: replace the frequency blocks in `ArchivedBillsPage.frequency`, `BillTemplateForm.frequency`, `BillTemplateRow.frequency`, `Frequencies` in en/pl/de; exact key parity.
- e2e: `helpers.ts` keeps `monthly` default; new spec `12-recurrence-intervals.spec.ts`: create a weekly bill (first payment date = first day of the current month) → payments list shows ≥4 rows for the bill and the row badge reads the weekly label; create an every-5-years bill → row shows the yearly label with count 5.

## Tests (backend)

- `test_recurrence_service.py`: rewrite `_next_period`/active-period tests for units+intervals; add weekly occurrence lists (month boundaries, interval 2), month-end clamping (Jan 31 + 1 month), `generate_next_instance` weekly + idempotency on `(bill_id, due_date)`, tombstone-per-due-date.
- `test_bills_create.py`: replace the `weekly`-is-invalid test with e.g. `daily`; add weekly requires `start_date` (422), interval bounds per unit (422), weekly backfill from a past start date.
- `test_bill_update_restore.py`: weekly schedule-change recompute (future unpaid move, paid untouched).
- `test_generate_instances.py`: weekly generates all occurrences; month-anchored with intervals 2/3 still correct.
- `test_stats.py`: forecast counts weekly occurrences per month.
- `test_restore.py`: legacy `every_2_months`/`quarterly` normalize to monthly+interval; v5 round-trip includes `interval_count`/`start_date`.
- `test_reminder_job.py`: weekly instances each fire independently (per-due-date flags).

## Docs

- `AGENTS.md` hard rule (idempotency key).
- `context/foundation/prd.md` FR-003 wording: frequency + interval (weekly/monthly/yearly, every N).
- `README.md` / `context/foundation/test-plan.md` references only if they state the old enum values.

## Verification

```
cd backend && nix shell nixpkgs#python313 -c bash -c 'export UV_PYTHON=python3.13; nix run nixpkgs#uv -- run black --check --target-version py313 .; nix run nixpkgs#uv -- run mypy app'
cd frontend && nix shell nixpkgs#nodejs_22 -c bash -c 'npm run lint; npm run build'
```

## Out of scope

- Daily recurrences.
- Changing `period` granularity or any month-based query.
- Grouping weekly occurrences in the monthly summary email.
- Recurrence editing UI beyond the form fields above.
