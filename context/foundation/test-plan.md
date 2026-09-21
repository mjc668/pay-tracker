# Test Plan

> Phased test rollout for this project. Strategy is frozen at the top
> (§1–§5); cookbook patterns at the bottom (§6) fill in as phases ship.
> Read before writing any new test.
>
> Refresh: re-run `/10x-test-plan --refresh` when stale (see §8).
>
> Last updated: 2026-06-17 (Phase 3 complete)

---

## 1. Strategy

Tests follow three non-negotiable principles for this project:

1. **Cost × signal.** The cheapest test that gives a real signal for the
   risk wins. Do not promote to e2e because e2e "feels safer." Do not put a
   vision model on top of a deterministic visual diff that already catches
   the regression.
2. **User concerns are first-class evidence.** Risks anchored in "the team
   is worried about X, and the failure would surface somewhere in <area>"
   carry the same weight as PRD lines or hot-spot data.
3. **Risks are scenarios, not code locations.** This plan documents *what
   could fail* and *why we believe it's likely* — drawn from documents,
   interview, and codebase *signal* (churn, structure, test base). It does
   NOT claim to know which line owns the failure. That knowledge is
   produced by `/10x-research` during each rollout phase. If the plan and
   research disagree about where the failure lives, research is the
   ground truth.

Hot-spot scope used for likelihood weighting: `backend/app/`, `frontend/src/`
(78 commits / last 30 days; `.venv/`, `.next/`, `node_modules/` excluded).

---

## 2. Risk Map

The top failure scenarios this project must protect against, ordered by
risk = impact × likelihood. Risks are failure scenarios in user / business
terms, not test names. The Source column cites the *evidence that surfaced
this risk* — never a specific file as "where the failure lives" (that is
research's job, see §1 principle #3).

| # | Risk (failure scenario) | Impact | Likelihood | Source (evidence — not anchor) |
|---|-------------------------|--------|------------|--------------------------------|
| 1 | Marking a payment as paid succeeds but the next-period instance is silently never created; the bill disappears from the dashboard without error | High | High | US-01, FR-006, FR-009; interview Q1, Q3; `backend/app/services` hot-spot (16 commits/30d) |
| 2 | Recurrence period math produces a wrong due date at month boundaries (e.g. `due_day=31` in February, `due_day=28` in a leap year, December→January year-rollover) | High | High | Interview Q2, Q3; `backend/app/services` hot-spot (16 commits/30d) |
| 3 | A payment instance endpoint (mark-paid, revert, delete) accepts an instance_id belonging to a different user and performs the mutation — IDOR on per-instance operations | High | Medium | FR-020, abuse lens; `backend/app/routers` hot-spot (29 commits/30d) |
| 4 | An existing test passes on SQLite in-memory but the same assertion fails on PostgreSQL due to constraint, type-coercion, or date-arithmetic divergence | High | Medium | Interview Q2; `backend/tests/` test base uses SQLite StaticPool |
| 5 | Restore from a JSON backup silently drops or corrupts payment instances; or XLSX export omits rows without raising an error | High | Medium | FR-010, FR-011; interview Q1, Q4; `context/archive/2026-06-15-data-restore` |
| 6 | Adding a new field to the backup schema (as occurred v2→v3) causes restore of older exports to fail or default incorrectly | Medium | Medium | `context/archive/2026-06-16-email-reminders` (v2→v3 guard); interview Q3 |
| 7 | The core payment-tracking loop (create template → mark paid → next instance visible) regresses in the frontend and is not caught because the frontend has zero test coverage | High | Low | FR-007, FR-008, FR-009; interview Q4; `frontend/src/app/dashboard` hot-spot (19 commits/30d) |

### Risk Response Guidance

| Risk | What would prove protection | Must challenge | Context `/10x-research` must ground | Likely cheapest layer | Anti-pattern to avoid |
|------|-----------------------------|----------------|--------------------------------------|-----------------------|-----------------------|
| #1 | Calling mark-paid on an instance causes exactly one new instance to appear for the correct next period; a second call produces no duplicate | Assume "mark-paid returns 200" implies the next-period instance was created | Entry point for instance creation after mark-paid; idempotency guard (bill_id, due_date); paused-template guard; one_off guard | Unit test on the recurrence service functions directly | Happy-path only — must also test paused, one_off, and already-existing next-period cases |
| #2 | `due_day=31` in Feb returns the last day of Feb; Dec→Jan correctly increments year; leap-year Feb 29 handled | Assume "works for common due_day values" covers boundary cases | The period math functions and their edge-case inputs; how due_day clamping is implemented | Pure Python unit tests (no DB needed) | Implementation mirror — do not copy the production formula as the expected value; derive expected dates independently |
| #3 | User B's attempt to mark-paid, revert, or delete User A's payment instance returns 403; the mutation does not execute | Assume "overall user-scoping integration test" covers per-instance mutations | Which endpoints load an instance by raw id, and what ownership check (if any) follows the load | Integration test per mutation endpoint with two-user fixture | Test only list-level isolation, not instance-level; miss the gap between "authenticated" and "owns this resource" |
| #4 | All tests pass against a real PostgreSQL container, not just SQLite; any constraint or type behavior that differs is visible | Assume SQLite StaticPool test passage implies PostgreSQL correctness | Differences in SQLite vs PostgreSQL for: RETURNING, unique-constraint conflict handling, date arithmetic, cascade behavior | Migrate conftest fixture to PostgreSQL (testcontainers or Docker Compose service) | Leave SQLite as the test DB and add more tests on top — structural fix, not more SQLite tests |
| #5 | Exporting then restoring produces the exact same set of instances (same ids, amounts, periods, statuses) as the original; export row count matches template × period combinations | Assume "restore runs without error" means all rows were restored | The restore endpoint's row-counting and collision-handling logic; how XLSX export iterates instances | Integration test: seed → export → restore to empty DB → compare | Assert only status code; miss silent row drop or field truncation |
| #6 | A v2 backup (no reminder fields) restores correctly with reminder fields defaulting to False; a v3 backup restores with fields intact | Assume current restore code handles all previous versions | The schema_version guard logic and how missing fields are handled per version | Integration test with fixture backup files at each version | Test only the current schema version |
| #7 | A Playwright test completes the full bill-tracking loop: create template → navigate to payments → mark paid → new instance appears for next month | Assume "backend tests pass" means the frontend flow works end-to-end | API contract between frontend fetch calls and backend responses; auth session handling in the Next.js app | Playwright e2e (the frontend has no cheaper layer that catches route + state issues) | Snapshot tests that capture DOM structure — they break on every layout change and catch nothing about flow correctness |

---

## 3. Phased Rollout

Each row is a discrete rollout phase that will open its own change folder
via `/10x-new`. Status moves left-to-right through the values below; the
orchestrator updates Status as artifacts appear on disk.

| # | Phase name | Goal (one line) | Risks covered | Test types | Status | Change folder |
|---|------------|-----------------|---------------|------------|--------|---------------|
| 1 | Recurrence unit tests | Prove period math and next-instance generation are correct at all boundary cases | #1, #2 | unit | done | context/archive/2026-06-17-testing-recurrence-unit/ |
| 2 | PostgreSQL integration baseline | Replace SQLite fixture with real PostgreSQL; add per-endpoint IDOR integration tests | #3, #4 | integration | done | context/archive/2026-06-17-testing-postgresql-integration/ |
| 3 | Export/restore round-trip | Prove backup→restore is lossless and backward-compatible with v2 exports | #5, #6 | integration | done | context/changes/testing-export-restore-round-trip/ |
| 4 | Frontend E2E critical paths | Catch regressions in the core payment loop and auth flows from the user's perspective | #7 | e2e | not started | — |

---

## 4. Stack

The classic test base for this project. AI-native tools (if any) carry a
`checked:` date so future readers can see which lines need re-verification.
Recommendations in this section are grounded in local manifests/configs
and the MCP/tools actually exposed in the current session.

| Layer | Tool | Version | Notes |
|-------|------|---------|-------|
| Backend unit + integration | pytest | ≥ 8.0 | Configured in `backend/pyproject.toml`; test files in `backend/tests/` |
| Backend HTTP client (tests) | httpx | ≥ 0.28 | Used with FastAPI `TestClient` for router-level integration tests |
| Backend DB fixture | SQLite StaticPool | — | Current; Phase 2 migrates this to PostgreSQL |
| Frontend unit | none yet | — | See §3 Phase 4 |
| Frontend e2e | Playwright | none yet | See §3 Phase 4; to be added as a `devDependency` in `frontend/package.json` |
| Accessibility | none yet | — | Not in current rollout scope |

**Stack grounding tools (current session):**
- Docs: none — no Context7/framework docs MCP available in this session; checked: 2026-06-17
- Search: none — no Exa.ai/web search MCP available in this session; checked: 2026-06-17
- Runtime/browser: none — no Playwright MCP in session; checked: 2026-06-17
- Provider/platform: none — no GitHub/Supabase/Cloudflare MCP available; checked: 2026-06-17

---

## 5. Quality Gates

The full set of gates that must pass before a change reaches production.
"Required after §3 Phase N" means the gate is enforced once that rollout
phase lands; before that, the gate is `planned`.

| Gate | Where | Required? | Catches |
|------|-------|-----------|---------|
| lint + typecheck (ESLint, mypy) | local + CI | required now | syntactic / type drift |
| backend unit + integration | local + CI | required after §3 Phase 1 | recurrence logic regressions, IDOR, data-integrity bugs |
| e2e on critical flows | CI on PR | required after §3 Phase 4 | broken payment loop, auth regression, frontend route failures |
| pre-prod smoke (manual) | between merge + prod | recommended | environment-specific failures (SMTP, PostgreSQL prod config) |

---

## 6. Cookbook Patterns

How to add new tests in this project. Each sub-section is filled in once
the relevant rollout phase ships; before that, the sub-section reads
"TBD — see §3 Phase N."

### 6.1 Adding a backend unit test (recurrence / pure logic)

TBD — see §3 Phase 1. Pattern will cover: testing period math and
next-instance generation independently of the DB, using only Python
objects and date arithmetic.

### 6.2 Adding a backend integration test (router / DB)

TBD — see §3 Phase 2. Pattern will cover: PostgreSQL fixture setup,
two-user IDOR test shape, asserting both the 403 response and the
absence of the mutation side-effect.

### 6.3 Adding a backup/restore test

TBD — see §3 Phase 3. Pattern will cover: fixture backup files per
schema version, seed→export→restore→compare round-trip, and how to
assert row-level completeness rather than just status codes.

### 6.4 Adding an e2e test (Playwright)

TBD — see §3 Phase 4. Pattern will cover: Playwright config, auth
setup, how to assert the next-period instance appearance after
mark-paid, and the locator hierarchy (`getByRole` / `getByLabel` first).

### 6.5 Per-rollout-phase notes

(Filled in as phases complete.)

---

## 7. What We Deliberately Don't Test

No explicit exclusions were requested in the Phase 2 interview (Q5 answer:
"I want coverage everywhere"). The following items are low-priority
given cost × signal, but are not blocked:

- **Alembic migrations** — framework-managed; test only if a migration
  has custom data logic. Re-evaluate if a migration performs row
  transforms.
- **Pydantic schema serialization** — framework guarantees field
  mapping; test at the router level where the schema is exercised end-to-end.
- **SMTP happy-path e2e (sending a real email)** — SMTP is off in test
  environments; the reminder-job tests already mock the send call.
  Re-evaluate if a new email template requires layout or encoding
  correctness.

---

## 8. Freshness Ledger

- Strategy (§1–§5) last reviewed: 2026-06-17
- Stack versions last verified: 2026-06-17
- AI-native tool references last verified: 2026-06-17 (none used)

Refresh (`/10x-test-plan --refresh`) when:

- a new top-3 risk surfaces from the roadmap or archive,
- a recommended tool's `checked:` date is older than three months,
- the project's tech stack changes (new framework, new test runner),
- §7 negative-space no longer matches what the team believes.
