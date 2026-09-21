# Editable Categories Implementation Plan

## Frozen contract

- New per-user table `categories`: `id, user_id (FK users.id ON DELETE CASCADE), key: str|None (String(50)), name: str|None (String(100)), is_archived: bool default false, created_at`.
  - Default categories: `key` set, `name` NULL unless renamed. Custom: `key` NULL, `name` set.
  - Unique `(user_id, key)` (NULLs distinct) and `(user_id, name)` (NULLs distinct); service also rejects duplicate names case-insensitively.
- `BillTemplate.category_id: int` FK → `categories.id`; the old `category` string column is dropped.
- **Label rule** (frontend): `category.name ?? t("Categories." + category.key)`; fallback to `""` when both null (cannot happen).
- **Order**: `GET /categories` returns a stable order (defaults then customs, each by name/key); the frontend sorts all groupings/filters alphabetically by rendered label with `localeCompare`.
- **Defaults seeding**: `ensure_default_categories(db, user)` is idempotent and called on registration and from `GET /categories`. The 9 keys: housing, utilities, insurance, subscriptions, entertainment, transport, healthcare, education, other.
- **Delete semantics**: `DELETE /categories/{id}` → 204 when unused; 400 with a clear message when any template references it. `PATCH` can rename (`name`) and archive/unarchive (`is_archived`). Archived categories stay on existing bills/stats, are rejected for new bill create/update (422), and are hidden from pickers by default (`GET /categories?include_archived=false`).
- **Legacy API compatibility** (keeps existing tests/e2e/demo working): `BillTemplateCreate`/`Update` accept either `category_id: int` (preferred) or `category: str` (legacy key, resolved to the user's default category, creating it if absent); providing neither → 422; `category_id` wins if both. Responses always carry a nested `category`.
- **Backup** `schema_version: 6`; `BackupTemplate.category` stays `str|None` and holds the category `key` for defaults or the `name` for customs. Restore resolves each distinct value per user: default key → that category (create if missing), otherwise custom name (case-insensitive find or create), `None`/unknown → `other`. Restore never deletes the user's categories. Versions 2–5 accepted.
- Response shape: `CategoryOut {id: int, key: str | None, name: str | None, is_archived: bool}`; `BillTemplateOut.category: CategoryOut`; `PaymentInstanceOut.category: CategoryOut`.

## Backend

1. `app/models/category.py` (new) + `app/models/bill.py`: replace the enum/column with `category_id` + relationship; drop `BillCategory` (replace usages with a default-keys constant in `app/services/categories.py`).
2. `app/services/categories.py` (new): `DEFAULT_CATEGORY_KEYS`, English display names, `ensure_default_categories`, `list_categories`, `create_category`, `rename_category`, `set_archived`, `delete_category` (unused only), `resolve_backup_value`, `get_for_user` (ownership + archived checks), and `category_label(language, category)` used by xlsx.
3. `app/schemas/category.py` (new): `CategoryOut`, `CategoryCreate` (trimmed, 1–50 chars), `CategoryUpdate` (name and/or is_archived). Update `app/schemas/bill.py`: `BillTemplateCreate/Update` accept `category_id`/legacy `category`; `BillTemplateOut.category: CategoryOut`; `PaymentInstanceOut.category: CategoryOut`; `BackupTemplate.category` unchanged.
4. `app/routers/categories.py` (new): `GET /categories` (with `include_archived`, ensures defaults), `POST`, `PATCH`, `DELETE`; register in `app/main.py`. Also call `ensure_default_categories` in `app/routers/auth.py:register`.
5. `app/routers/bills.py`: resolve/validate category on create/update (ownership, not archived); eager-load `template.category` in the payments list; `_to_out` includes nested categories. Legacy `category` string resolves via the service.
6. `app/services/stats.py`: `by_category` groups by `category_id` and returns `CategoryStat {category: CategoryOut, paid_total, due_total}`; ordering unchanged (paid desc, then label).
7. `app/routers/export.py`: xlsx writes `category_label(language, category)` (default keys translated with a backend map matching the frontend `Categories` messages; customs as stored). Backup v6 export writes key-or-name; restore resolves per the contract. Remove `_coerce_category`.
8. Migration `alembic/versions/f6a7b8c9d0e1_editable_categories.py`, `down_revision = "e5f6a7b8c9d0"`:
   - create `categories` (+ constraints), seed defaults for every existing user;
   - add nullable `bill_templates.category_id`, backfill by matching `category` (key) per user, fall back to that user's `other`;
   - set NOT NULL + FK, drop `bill_templates.category`.
   - downgrade: re-add the string column, populate from key/name (`COALESCE(key,'other')`), drop FK/column/table (best-effort for custom names).
9. Tests: new `tests/test_categories.py` (CRUD, seeding idempotency, scoping, duplicate names 422, delete-in-use 400, archive hides from default list, archived rejected on bill create); update bill/stats/export/restore tests for `category_id` while keeping legacy-string creation covered; restore tests for v6 round-trip, custom names, and v2–v5 legacy mapping; xlsx label test for a default key in pl and a custom name.

## Frontend

1. `src/lib/categories-api.ts` (new): `Category` type + `fetchCategories(includeArchived?)`, `createCategory`, `updateCategory`, `deleteCategory`; `categoryLabel(category, t)` helper.
2. `src/lib/categories.ts`: remove the hardcoded order; add a palette indexed by position (`categoryColor(index)`) and `sortCategories(categories, locale)` (alphabetical by label); keep the border palettes.
3. Types: `BillTemplateCreate` uses `category_id`; `BillTemplateOut.category: Category`; `PaymentInstanceOut.category: Category`.
4. `CategoryCombobox.tsx`: data-driven select of non-archived categories (alphabetical) with an inline "Add new…" option that creates a category and selects it; used by the bill form (form still sends `category_id`).
5. Bills page (`page.tsx`, `archived/page.tsx`): fetch categories alongside templates; grouping headers, counts and filter options use `categoryLabel`/palette/sorted list. Payments page: same for grouping, filters and calendar chips (`PaymentRow` unchanged apart from types).
6. Stats `CategoryBars.tsx`: render labels via the category object, colors by index.
7. Settings: new `src/components/settings/CategoriesTile.tsx` (list with rename inline, archive/unarchive, delete when unused, add new) wired into the settings page like the other tiles; i18n keys.
8. e2e: helpers keep working via the legacy `category` string (verify); new `tests/e2e/13-editable-categories.spec.ts`: add a custom category in Settings, create a bill with it via the form, confirm the bills grouping label; rename it and see the bill relabel; archive it (gone from the picker); delete an unused one. Existing specs must keep passing.

## i18n

Keep `Categories.<key>` for the nine defaults. Add `SettingsPage.categories` (tile title/add/rename/archive/unarchive/delete/deleteBlocked/errors) and `BillTemplateForm.categoryAdd`-style keys in en/pl/de with exact parity.

## Verification

```
cd backend && nix shell nixpkgs#python313 -c bash -c 'export UV_PYTHON=python3.13; nix run nixpkgs#uv -- run black --check --target-version py313 .; nix run nixpkgs#uv -- run mypy app'
cd frontend && nix shell nixpkgs#nodejs_22 -c bash -c 'npm run lint; npm run build'
```

## Out of scope

- Per-category colors chosen by the user (palette is positional).
- Manual ordering (alphabetical only).
- Household-wide shared categories (categories stay per-user, consistent with data isolation).
- Category budgets/limits.
