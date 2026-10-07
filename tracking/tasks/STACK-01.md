# STACK-01 — Verify stack ADRs, retire contradicted decision text, pin versions
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`stack`](../../docs/blueprint/modules/stack/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | — |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/stack/README.md`](../../docs/blueprint/modules/stack/README.md)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) to [0008](../../docs/adr/0008-entitlements-and-commercial-model.md) (all of them; this task checks them), plus [`docs/adr/README.md`](../../docs/adr/README.md)
4. [`tracking/OPEN-QUESTIONS.md`](../OPEN-QUESTIONS.md) and [`docs/blueprint/01-decisions.md`](../../docs/blueprint/01-decisions.md)

## Spec

The stack ADRs already exist (ADRs 0001–0008, revised 2026-10-07: greenfield build, Python backend, TypeScript frontends, no AIP code, schema or data). This task does **not** write new stack ADRs. It checks them against the owner's answers, retires the decision text they contradict through an errata note, pins the toolchain versions in one table and adds a lint so the record cannot drift.

- **files**:
  - docs/stack/versions.md (new: the versions table)
  - docs/blueprint/01-decisions.md (append an errata block only; owner text is not deleted)
  - docs/blueprint/07-task-conventions.md (fix the stale "migrations are TypeScript, not Alembic" line)
  - AGENTS.md (fix the stale "greenfield TypeScript rebuild" paragraph)
  - docs/adr/README.md (index row per ADR with its current status)
  - tracking/OPEN-QUESTIONS.md (mark Q0 answered; restate Q1 for the revised ADRs)
  - .python-version, .nvmrc
  - tools/ci/check_adrs.py (stdlib-only Python, no dependency on the uv workspace)
  - tools/ci/test_check_adrs.py (stdlib `unittest`)
  - .github/workflows/ci.yml (add a `docs` job, or create the file with only that job if ARCH-03 has not landed)
- **steps**:
  - 1. For each ADR 0001–0008, compare its **Status** line with the owner's answers in `tracking/OPEN-QUESTIONS.md` and the owner quote in ADR 0001. Where an answer exists, the ADR status must say `accepted` and quote or cite it. Where no answer exists, the status must say `owner to confirm` (currently 0003 queue, 0004 Vite for all apps, 0005 identity split, 0006 per-tenant KMS key, 0007 MVP cut, 0008 commercial model). Do not change any decision; if an ADR and an owner answer disagree, list the conflict in `tracking/OPEN-QUESTIONS.md` instead of resolving it.
  - 2. In `tracking/OPEN-QUESTIONS.md`, mark Q0 as answered ("Python backend, TypeScript frontends, AIP not used", 2026-10-07, ADR 0001) and rewrite Q1 so it asks the owner to confirm Procrastinate on Postgres (ADR 0003) in place of the "Redis queue (arq or Celery)" text. Remove the stale Kysely/BullMQ wording. Q4 (AIP source access) is answered by ADR 0001: agents do not read AIP.
  - 3. Append to `docs/blueprint/01-decisions.md` a block headed `## Errata (2026-10-07)` that starts with `<!-- errata: keep on regeneration -->` and has one line per superseded or reconciled decision, each naming the ADR: "Continue AIP FastAPI or rebuild in TypeScript" → ADR 0001 (Python backend, TS frontends, greenfield); "Background job runner: Redis queue (arq or Celery)" → ADR 0003 (Procrastinate, owner to confirm); "Frontend framework: Next.js" → ADR 0004 (Vite, owner to confirm); "Tenant-set and encryption key scheme: Shared key" → ADR 0006 (proposed); "Identity provider: Keycloak" plus "Local authentication: build in-app" → ADR 0005 (reconciled); "Orm and migration approach: Keep Alembic raw SQL" → ADR 0002 (consistent: Alembic raw SQL with SQLAlchemy Core). Leave the original owner lines untouched above it.
  - 4. Fix the two stale sentences: in `07-task-conventions.md` replace "(e.g. migrations are TypeScript, not Alembic — ADR 0002)" with "(e.g. Python backend, Vite frontends — ADR 0001, 0004)"; in `AGENTS.md` replace the "greenfield TypeScript rebuild ... translate it using the ADRs" paragraph with the ADR 0001 wording (Python backend, TypeScript frontends, no AIP code/schema/data; translate NestJS, Kysely, BullMQ, Next.js, `services/sidecar`, `backend/`, `frontend/` via the ADR 0001 table).
  - 5. Write `docs/stack/versions.md` with one table: `| Component | Version | Pinned in | Upgrade policy |`. Rows (exact patch versions are copied from `uv.lock` / `pnpm-lock.yaml` once ARCH-01 lands; until then record the major/minor shown): Python `3.12` (`.python-version`, `apps/api/pyproject.toml` `requires-python`), FastAPI (current stable, `uv.lock`), Pydantic `2.x`, SQLAlchemy `2.0.x`, asyncpg, Alembic `1.x`, Procrastinate (current major), PostgreSQL `16` (`pgvector/pgvector:pg16`), Node `22` LTS (`.nvmrc`, `engines.node`), pnpm (current major, `packageManager`), Vite (current major), React, TanStack Router, Vitest, Playwright. Write `.python-version` = `3.12` and `.nvmrc` = `22`.
  - 6. Write `tools/ci/check_adrs.py`. It reads every `docs/adr/NNNN-*.md` except `0000-template.md`, parses the number from the filename and the `- **Status:**` / `- **Date:**` / optional `- **Supersedes:**` header bullets, and fails when: two files share a number; a Status or Date bullet is missing; a Supersedes target number has no file; an ADR file is not listed in `docs/adr/README.md`; `01-decisions.md` lacks the `<!-- errata: keep on regeneration -->` marker (catches a blueprint regeneration that dropped it); the `Python` and `Node` rows of `docs/stack/versions.md` disagree with `.python-version` / `.nvmrc`. Output one line per finding, exit 1 on any finding.
  - 7. Add a `docs` job to `.github/workflows/ci.yml` running `python3 tools/ci/check_adrs.py` and `python3 -m unittest tools/ci/test_check_adrs.py`.
- **acceptance**:
  - Every owner decision line in `01-decisions.md` that an ADR changes or reconciles has exactly one errata line naming that ADR.
  - No file outside `docs/reviews/` and the errata block still describes the backend as TypeScript, NestJS, Kysely or BullMQ (`grep -rnE "NestJS|Kysely|BullMQ|TypeScript rebuild" AGENTS.md docs/blueprint/07-task-conventions.md docs/adr` returns nothing outside ADR 0001's translation table and "first version chose" history notes).
  - The queue (0003), Vite (0004), identity (0005), KMS (0006), MVP (0007) and commercial (0008) ADRs are explicitly marked as awaiting owner confirmation unless an answer is recorded.
  - `docs/stack/versions.md` exists and its Python and Node rows match the pin files.
- **tests**:
  - **unit**:
    - The header parser on ADR 0002's text returns `{number: 2, status: "accepted (matches owner decision ...)", date: "2026-10-07", supersedes: None}`.
    - The versions-table parser on `| Python | 3.12 | .python-version | minor bumps by ADR |` returns `{"Python": "3.12"}`.
  - **integration**:
    - Copy `docs/` to a temp dir and add `0002-duplicate.md`. Expected: exit 1 and output `duplicate ADR number 0002`.
    - Add `- **Supersedes:** 0042` to a temp copy of ADR 0003. Expected: exit 1 and output `0003 supersedes missing ADR 0042`.
    - Remove the errata marker from a temp copy of `01-decisions.md`. Expected: exit 1 and output `01-decisions.md is missing the errata block`.
    - Set `.nvmrc` to `20` in a temp copy. Expected: exit 1 and output `versions.md Node 22 != .nvmrc 20`.
    - Run on the committed tree. Expected: exit 0.
  - **e2e**:
    - CI `docs` job on the PR. Expected: green with the committed files; red on a throwaway commit that duplicates an ADR number.
