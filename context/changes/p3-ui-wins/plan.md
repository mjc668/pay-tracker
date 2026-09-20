# P3 UI Wins Implementation Plan

Phase 1 (parallel): backend + frontend A. Phase 2: frontend B (dashboard). All contracts below are frozen; agents must not change them.

## A. Default currency

### Backend
- `User.default_currency: Mapped[str | None] = mapped_column(String(10))` (nullable; add after `language_preference`).
- Hand-written Alembic migration (nullable column, no `server_default`) with `down_revision` = current head.
- `app/schemas/auth.py`: `UserProfileOut.default_currency: str | None`; `UserProfileUpdate.default_currency: str | None = None` with a validator: strip, uppercase, must match `^[A-Z0-9]{2,10}$` → otherwise 422. (`update_me` applies `exclude_unset` fields, so no endpoint change needed.)
- Tests: set/clear via `PATCH /auth/me`, invalid value 422, `/auth/me` round-trip.

### Frontend
- `BillTemplateForm` gains optional prop `defaultCurrency?: string`; initial-currency precedence becomes `initial?.currency ?? defaultCurrency ?? LOCALE_DEFAULT_CURRENCY[locale] ?? "EUR"`.
- Bills page fetches the profile (`fetchMe` from `@/lib/user-api`) and passes `defaultCurrency={profile?.default_currency ?? undefined}`.
- Settings → `ProfileTile` adds a "Default currency" row: select with presets PLN, EUR, USD, AUD + "Custom" (text input, uppercased), saved via `updateMe({ default_currency })`, reflecting the saved value from `profile`. Inline error on failure; uses the existing tile styling.

## B. Calendar

### Payments page (frontend A)
- Header view toggle: `List` | `Calendar` (segmented buttons, localStorage-free state).
- Calendar: month grid for `selectedMonth`, weeks starting Monday, day cells show instance chips (truncated bill name + amount; status colors from `PaymentRow`'s palette). Days with more than 3 instances show "+N".
- Selected-day panel below the grid renders the existing `PaymentRow` components for that day (so mark-paid/delete/history keep working). Default selection: today when in the displayed month, else the first day that has instances.
- Empty months show the existing "no payments" state.

### Dashboard mini-calendar (frontend B)
- Current-month grid widget with a status-colored dot per due date (one dot per instance, max 3 + "+N"), day numbers, weekday header; clicking the widget (or a day) links to `/dashboard/payments?month={period}`.
- Dashboard fetches `fetchPayments(currentMonth)` in addition to stats (`Promise.all`, tolerate payments failure so stats still render).

## C. Filters

### Payments page (frontend A)
- Filter bar above the list: status select (`all` | `unpaid` = upcoming+overdue | `overdue` | `paid`), category select (`all` + categories present), text search on `bill_name` (case-insensitive, trimmed).
- Client-side filtering of the already-fetched month. When filters yield nothing, show a distinct "no matches" state (not the "no bills" state) with a clear-filters action.
- Category grouping and collapse behavior stay as-is for filtered results.

### Bills page (frontend A)
- Filter bar above the grouped list: category select (`all` + present), state select (`all` | `active` | `paused`), text search on `name`.
- Grouping and collapse stay; "no matches" state distinct from the empty list; filters do not affect the archived page.

## D. Forecast on the trend chart

### Backend
- `GET /stats/overview` response gains `forecast: list[ForecastPoint]` where `ForecastPoint = {period: str, expected_total: Decimal}`.
- Exactly 6 points: `month+1` … `month+6` (independent of `months`; document in schema).
- `expected_total` = Σ `BillTemplate.amount` over the user's active templates (non-archived, non-paused, `frequency != one_off`) whose schedule is active in that period (`_bill_active_in_period`) and whose currency equals the primary currency. Existing instances do not subtract (it is an expectation, not a remainder).
- Reuse `app/services/recurrence.py:_bill_active_in_period`; do not duplicate recurrence math.

### Frontend (frontend B)
- `SpendTrendChart` renders 12 x positions: the 6 actual trend months, then the 6 forecast months. Actuals keep the existing paid area/line and due dashed line; the forecast is a third, dashed amber line spanning only the future points, starting after a vertical divider at the present boundary.
- Legend adds "Forecast". If every `expected_total` is 0, omit the line, divider and legend entry.
- X labels rotate to short month names for all 12 points (keep readable at mobile width).

## E. Series generator (pre-generate future instances)

### Backend
- `POST /bills/generate-instances`, request `GenerateInstancesRequest { months: int = 6 (ge=1, le=24), bill_ids: list[int] | None = None }`.
- Default (no `bill_ids`): all of the user's eligible templates — non-archived, non-paused, `frequency != one_off`. With `bill_ids`: only those, and any id not owned by the user → 404.
- Range: from `current_utc_month + 1` through `+ months` inclusive. Reuses `backfill_template_instances` per template (idempotent via `(bill_id, period)`; never resurrects soft-deleted tombstones).
- Change `backfill_template_instances` to return the number of instances it actually created (currently returns None; update existing callers as needed).
- Response `GenerateInstancesOut { created: int, bill_count: int, months: int }`.
- Tests: creates missing periods only (idempotent second call → `created == 0`), respects paused/archived/one-off, ownership 404, bounds 422, active templates generate the expected periods for monthly/every-2/quarterly/annual.

### Frontend (frontend A)
- Bills page header button "Generate payments" opens `GenerateInstancesDialog`: months number input (1–24, default 6), checkbox list of eligible templates (active, unpaused, recurring; all checked by default), submit → `generateInstances()` from `bills-api.ts`, success shows "Created N payment(s)" inside the dialog and refreshes the list.
- Disabled state when there are no eligible templates, with an explanatory line.

## F. Tests / e2e

- Backend: forecast cases in `tests/test_stats.py` (monthly/quarterly/annual active periods, paused/archived/one-off excluded, other currency excluded, exactly 6 points oldest-first); `tests/test_generate_instances.py`; default-currency tests in `tests/test_auth_endpoints.py`.
- Frontend e2e (frontend A): `tests/e2e/10-payment-calendar-filters.spec.ts` (toggle to calendar, chips render, selected-day rows; filters narrow the list, clear-filters restores) and `tests/e2e/11-bill-filters-generator.spec.ts` (filter by name/state; generate 2 months for a monthly bill → dialog reports creation, payments page later shows the future month instance).
- Frontend B updates `tests/e2e/09-dashboard.spec.ts` to assert the mini-calendar and (when applicable) the forecast legend, without breaking existing assertions.

## G. i18n

New keys under `PaymentsPage`, `PaymentRow`, `BillsPage`, `BillTemplateForm`, `SettingsPage`, `Dashboard` in `messages/en.json`, `pl.json`, `de.json`. Key parity is mandatory. Phase 1 agents edit only their own sections; frontend B edits `Dashboard` only.

## Verification Commands

```
cd backend && nix shell nixpkgs#python313 -c bash -c 'export UV_PYTHON=python3.13; nix run nixpkgs#uv -- run black --check --target-version py313 .; nix run nixpkgs#uv -- run mypy app'
cd frontend && nix shell nixpkgs#nodejs_22 -c bash -c 'npm run lint; npm run build'
```

## What We're NOT Doing

- No chart/date libraries; no new dependencies.
- No server-side filtering/pagination (month and bill lists are household-scale).
- No day-level deep link (`?month=` only).
- No changes to recurrence semantics, reminders, or exports.
- No per-currency stats changes (existing primary-currency rule stands).
