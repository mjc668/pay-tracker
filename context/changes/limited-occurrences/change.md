---
change_id: limited-occurrences
title: Limited recurrence — set the total number of payments per bill
status: in-progress
created: 2026-09-22
updated: 2026-09-22
---

## Notes

Some recurring bills only run a fixed number of times (e.g. a 4-payment instalment plan). Add an optional per-template cap: `max_occurrences` (null = endless). The bill form gains a "Set number of payments" checkbox with a count input; all generation paths stop at the cap, the dashboard forecast stops counting beyond it, and backups round-trip the field (schema v7).
