---
change_id: payment-ledger
title: Payment ledger — multiple payment events per instance with recording UI
status: in-progress
created: 2026-09-20
updated: 2026-09-20
---

## Notes

Roadmap P1. `PaymentInstance` currently stores a single paid state (`status`, `paid_at`, `paid_amount`, `notes`) and "mark as paid" overwrites it. This change introduces a `payments` table of individual payment events per instance, so partial payments and several payments across a period are recorded with their own amount, date, and note. Instance paid fields become a denormalized summary derived from the ledger, preserving compatibility with reminders, exports, restore, and the existing API. The payments UI gains a date field, partial-payment support, and a per-instance payment history with per-event deletion. Backfill: every currently-paid instance gets one ledger row.
