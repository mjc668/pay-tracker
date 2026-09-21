# Repository Guidelines

Pay Tracker is a household bill-tracking PWA. Stack: Next.js 16 (App Router, TypeScript, Tailwind) frontend, FastAPI + Python 3.13 backend, PostgreSQL 17 co-located in the backend container.

## Hard Rules

- **Next.js 16 has breaking changes from training data.** Before writing any frontend code, read `@frontend/AGENTS.md` — its warning is load-bearing.
- **Recurrence auto-generation is idempotent.** The key is `(bill_id, due_date)`. Never insert a `PaymentInstance` without checking for an existing row on that pair — see `@backend/app/services/recurrence.py`. (`period` stays `"YYYY-MM"` and is derived from `due_date`.)
- **Archive templates, never delete.** Set `is_archived = True` on `BillTemplate`; hard deletes cascade to payment history.
- **Migrations run automatically on container start.** `alembic upgrade head` fires in the supervisord uvicorn command. New model changes require a new revision: `docker compose exec backend uv run alembic revision --autogenerate -m "<desc>"`.
- **Use SQLAlchemy 2.0 `Mapped[T]` / `mapped_column()` style.** The 1.x `Column()` pattern will pass linting but is wrong for this codebase — see `@backend/app/models/bill.py`.

## Project Structure

```
frontend/   Next.js 16 PWA — App Router, src/, Tailwind
backend/    FastAPI — app/{routers,models,schemas,services,core}/
            PostgreSQL 17 data at /var/lib/postgresql/17/main (named volume)
infra/      nginx configs, compose overrides (empty — future use)
context/    10x workflow artifacts (PRD, tech-stack, bootstrap log)
```

See `@context/foundation/prd.md` for domain rules and `@context/foundation/tech-stack.md` for stack rationale.

## Build & Development Commands

- `docker compose up --build` — start everything (backend `8010`, frontend `3010`)
- `docker compose down -v && docker compose up --build` — clean start, wipes DB volume
- `cd frontend && npm run dev` — frontend only, no Docker
- `cd backend && uv run uvicorn app.main:app --reload` — backend only, no Docker
- `cd frontend && npm run lint` — ESLint
- `docker compose exec backend uv run alembic revision --autogenerate -m "<desc>"` — new migration (then `upgrade head`)

API docs: `http://localhost:8010/docs`.

## Coding Style & Conventions

- **Frontend:** No `any`. Do not add a `pages/` directory — this project is App Router only. Components in `frontend/src/`.
- **Backend:** All request/response types use Pydantic schemas in `backend/app/schemas/`. Never use raw dicts as router return types. Routers in `backend/app/routers/`, business logic in `backend/app/services/`.
- **Env vars:** copy `.env.example` → `.env`; never commit `.env`.

## Pre-commit Hooks

After cloning, install the hooks once:

```bash
pip install pre-commit
pre-commit install          # file-staged secrets scan on git commit
pre-commit install --hook-type commit-msg   # conventional-commit lint on commit message
```

Hooks defined in `.pre-commit-config.yaml`:
- `detect-secrets` — prevents accidental secret commits; baseline in `.secrets.baseline`
- `conventional-pre-commit` — enforces Conventional Commits message format

To update the secrets baseline after an intentional addition: `detect-secrets scan > .secrets.baseline`.

## Commit Guidelines

Conventional Commits prefix required: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`. One-line subject under 72 characters. Reference the PRD FR number in the body when implementing a functional requirement (e.g. `Implements FR-009`).
