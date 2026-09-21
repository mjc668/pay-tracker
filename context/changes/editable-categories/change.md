---
change_id: editable-categories
title: Editable categories — per-user table with translatable defaults
status: in-progress
created: 2026-09-21
updated: 2026-09-21
---

## Notes

Replace the fixed `BillCategory` enum with a per-user `categories` table. The nine built-ins are seeded per user with a `key` so the UI keeps translating them (`Categories.<key>` in en/pl/de); renaming stores a `name` override and custom categories carry a name only. Bills reference `category_id`, so renames relabel history automatically. Categories archive (history preserved) and can be hard-deleted only when unused. Backups stay string-based: defaults export their key, custom categories their name; restore finds-or-creates and legacy backups keep working. Management lives in a Settings tile plus an inline "Add new…" in the bill form picker. Display order is alphabetical by rendered label (client-side).
