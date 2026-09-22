# Dashboard Stats (P2) Implementation Plan

## Overview

Replace the dashboard's nav-tile grid with a stats overview backed by one read-only endpoint. Charts are hand-written SVG/CSS — no chart or date library is added. Stats cover the user's primary currency only; a note lists other currencies present.

## Frozen API Contract

### `GET /stats/overview?month=YYYY-MM&months=6`

- `month` optional, defaults to the current month; validated `^\d{4}-\d{2}$` → 422 otherwise.
- `months` optional, default 6, clamped/validated `1..24`.
- Auth: `current_user`; read-only (no instance syncing).

Response (`StatsOverviewOut`):

```json
{
  "month": "2026-09",
  "months": 6,
  "currency": "AUD",
  "other_currencies": ["PLN"],
  "summary": {
    "due_total": "1234.56",
    "paid_total": "800.00",
    "remaining_total": "434.56",
    "total_count": 8,
    "paid_count": 5,
    "upcoming_count": 1,
    "overdue_count": 2,
    "overdue_total": "300.00"
  },
  "trend": [
    { "period": "2026-04", "paid_total": "500.00", "due_total": "600.00" }
  ],
  "by_category": [
    { "category": "utilities", "paid_total": "200.00", "due_total": "250.00" }
  ],
  "attention": [
    {
      "instance_id": 12, "period": "2026-08", "bill_name": "Electricity",
      "due_date": "2026-08-15", "amount": "120.00", "paid_amount": null,
      "remaining": "120.00", "status": "overdue"
    }
  ]
}
```

Rules:
- **Primary currency** = the currency with the most non-archived templates for the user; ties broken alphabetically. No templates → `"PLN"`, empty stats. `other_currencies` = all other distinct template currencies, sorted.
- **summary** covers `month`, primary currency, `is_deleted == false`:
  - `due_total = Σ amount`, `paid_total = Σ (paid_amount or 0)`, `remaining_total = Σ max(amount - (paid_amount or 0), 0)`.
  - Effective overdue = `status == overdue` OR (`status == upcoming` AND `due_date < today`) — mirrors `list_payments`.
  - `overdue_total` = Σ remaining of effective-overdue rows.
  - `upcoming_count` = effective upcoming rows; `paid_count` = `status == paid`.
- **trend** = exactly `months` points ending at `month`, oldest first:
  - `paid_total` = Σ `payments.amount` where `paid_on` is inside the period (ledger-based), primary currency.
  - `due_total` = Σ `payment_instances.amount` for that `period`.
- **by_category** = over the whole trend window (all `months`), primary currency:
  - `paid_total` = Σ ledger payments by category; `due_total` = Σ instances by category. Rows with both zero are omitted; sorted by paid_total desc, then category.
- **attention** = primary currency, not deleted, not fully paid, and either overdue (`due_date < today`) or due within 30 days. Sort `due_date` asc, tie-break `id`; limit 10. `status` is computed (`overdue` if `due_date < today` else `upcoming`); `remaining = max(amount - paid_amount or 0, 0)`; include `period` for deep links.
- Decimals serialize as strings (Pydantic), dates as `YYYY-MM-DD`, matching the existing API.

## Backend

- `app/schemas/stats.py` (new): `StatsSummary`, `TrendPoint`, `CategoryStat`, `AttentionItem`, `StatsOverviewOut`. Decimal fields as `Decimal`, `category: BillCategory`.
- `app/routers/stats.py` (new): router prefix `/stats`, tag `stats`; `GET /overview`. Register in `app/main.py` next to the other routers.
- Queries: use aggregates (`func.sum`, `func.count`) with joins `Payment → PaymentInstance → BillTemplate` and direct instance queries; household scale, so a handful of grouped queries is fine. Use `selectinload`-free aggregation (SQL-level sums). `today = date.today()`.
- No model or migration changes.

## Frontend

### Types/API
`src/lib/stats-api.ts` (new): `StatsOverview` interfaces mirroring the response (amounts as `string`), `fetchStatsOverview(month?: string): Promise<StatsOverview>` via `apiFetch`.

### Currency
Add `"AUD"` to `PRESET_CURRENCIES` in `src/components/bills/BillTemplateForm.tsx` (keep order EUR, PLN, USD, AUD). No backend validation change (currency is free-form `str`).

### Dashboard page (`src/app/dashboard/page.tsx`)
Rewrite as the overview (keep `useTranslations("Dashboard")`):
- Fetch stats on mount in `useEffect`; loading skeleton (`animate-pulse` cards) and inline red error with retry, matching the payments page pattern. Reuse the existing `fetchStatsOverview` error handling (SessionExpiredError already handled globally).
- Sections in order: monthly summary cards, spend trend, category breakdown, attention list. Show a CTA ("Add your first bill" → `/dashboard/bills`) when `total_count === 0` for the month and there are no trend values.
- Currency note when `other_currencies.length > 0`.

### Components (`src/components/dashboard/`)
- `SummaryCards.tsx` — four cards: Due, Paid, Remaining, Overdue (count + amount). Grid `sm:grid-cols-2 lg:grid-cols-4`; color accents consistent with existing tiles (emerald/blue/amber/red).
- `SpendTrendChart.tsx` — hand-rolled SVG area/line chart:
  - `viewBox="0 0 600 220"`, `className="w-full h-auto"`, y-axis 3–4 ticks from 0 to a rounded max, x labels = short month names derived from `period + "-01T00:00:00"` (client-fetched data, so no hydration concern).
  - Area path + stroke line in emerald, gradient fill (`<linearGradient>` with a `useId()`-derived id to avoid collisions), dots with native `<title>` tooltips, baseline gridline.
  - Optionally a dashed line for `due_total`; only if it stays readable. Legend: Paid (filled) / Due (dashed).
  - `role="img"` with `aria-label`; no external deps.
- `CategoryBars.tsx` — horizontal CSS bars (label, track, fill; no library), paid vs due per category, sorted desc, each row shows formatted amounts. Empty state text.
- `AttentionList.tsx` — overdue/upcoming rows: bill name, due date, amount/remaining, status badge; each row links to `/dashboard/payments?month={period}`; empty state when none.

### Payments page deep link
`src/app/dashboard/payments/page.tsx`: on mount, if `window.location.search` has `month=YYYY-MM` (validated), set `selectedMonth`/`selectedYear` from it. Use a mount effect with `window.location` (not `useSearchParams`) to avoid Suspense requirements.

### i18n
Add keys under `Dashboard` in `messages/en.json`, `pl.json`, `de.json` (all three, no missing keys): section titles, card labels, trend/category/attention labels, empty states, currency note, error/retry, CTA.

## Tests

Backend — new `tests/test_stats.py`:
- summary math: due/paid/remaining with a full payment, a partial payment and an unpaid overdue instance; counts.
- primary currency: dominant currency chosen, `other_currencies` listed; ties alphabetical.
- trend buckets ledger payments by `paid_on` (including a payment dated in a previous month) and lists `months` points oldest-first.
- by_category aggregation and ordering.
- attention: overdue + next-30-days selection, exclusion of paid/fully-paid and of other users' rows; limit and ordering.
- empty state (no templates) returns the default currency and zeroed/empty sections.
- invalid `month`/`months` → 422.

Frontend e2e — new `tests/e2e/09-dashboard.spec.ts` (check numbering against existing specs first):
- fresh user with a bill and a payment → summary cards show the paid amount, trend chart SVG renders (`role="img"`), category bars and/or empty states render.
- attention list shows an overdue/unpaid bill and links to the payments page with the right month.
- keep assertions deterministic (derive amounts/dates; avoid fixed months except relative to `new Date()`).

## Verification Commands

```
cd backend && nix shell nixpkgs#python313 -c bash -c 'export UV_PYTHON=python3.13; nix run nixpkgs#uv -- run black --check --target-version py313 .; nix run nixpkgs#uv -- run mypy app'
cd frontend && nix shell nixpkgs#nodejs_22 -c bash -c 'npm run lint; npm run build'
```

## What We're NOT Doing

- No chart/date libraries (no recharts, chart.js, date-fns, etc.).
- No range picker UI (fixed 6 months; endpoint accepts `months` for the future).
- No per-currency sections (primary currency only + note).
- No changes to existing endpoints, models, or migrations.
