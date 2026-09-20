---
change_id: dashboard-stats
title: Dashboard stats — dependency-free SVG charts and household overview
status: in-progress
created: 2026-09-20
updated: 2026-09-20
---

## Notes

Roadmap P2. The dashboard home (`/dashboard`) is currently only four navigation tiles. It becomes the household overview: this-month summary, a six-month spend trend drawn with hand-rolled SVG (no chart library), a category breakdown, and an upcoming/overdue attention list. A new read-only `GET /stats/overview` endpoint aggregates instances and the payment ledger. Stats are limited to the user's primary currency (most templates); other currencies are reported so the UI can show a note. AUD is added to the bill form's preset currencies.
