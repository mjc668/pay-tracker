---
change_id: recurrence-flexibility
title: Generalized recurrence — weekly + every-N months/years
status: archived
created: 2026-09-21
updated: 2026-09-21
archived_at: 2026-09-22T00:00:00Z
---

## Notes

Replace the fixed `BillFrequency` values (`monthly`, `every_2_months`, `quarterly`, `annual`, `one_off`) with units + interval: `weekly | monthly | annual | one_off` × `interval_count` (weeks 1–4, months 1–12, years 1–5). Weekly bills are anchored on a `start_date` ("first payment date") and produce 1–5 instances per month, which requires swapping the idempotency key from `(bill_id, period)` to `(bill_id, due_date)`; `period` stays `"YYYY-MM"` so every existing month-based query keeps working. Legacy values migrate: `every_2_months` → monthly/2, `quarterly` → monthly/3. Backup schema moves to v5 (adds `interval_count`, `start_date`) and normalizes legacy frequencies on restore. Breaking API/backup change → release v2.0.0.
