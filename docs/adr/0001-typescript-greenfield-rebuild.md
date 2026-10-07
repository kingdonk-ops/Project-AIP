# ADR 0001: TypeScript greenfield rebuild; Python only in the sidecar

- **Status:** accepted (owner decision)
- **Date:** 2026-10-07
- **Affects:** all modules and tasks

## Context

The owner chose "TypeScript rebuild" over continuing the FastAPI AIP codebase. Much of the blueprint
was written while that question was open, so it still carries Python-era artefacts: Alembic, arq/Celery,
SQLAlchemy, Pydantic, pytest/Hypothesis, `backend/app/...`, `frontend/src/...`, `module.toml` and
import-linter. Every reviewer flagged this (docs/reviews/). There is no AIP code in this repository.

## Decision

- The product is TypeScript end to end: Node 22, NestJS, Next.js/React, Zod, pnpm.
- Python is allowed **only** in `services/sidecar` (IFC, CAD, OCR), behind an HTTP + JSON Schema contract (ADR 0003).
- AIP's 48 phases are a **behavioural specification**. "Port from AIP" means re-implement the behaviour and
  prove it with golden tests. Migrating Kaefer's data out of AIP is a separate R1 task.

| Blueprint says | Use instead |
|---|---|
| Alembic / `migrations/versions/*.py` | `db/migrations/*.sql` (ADR 0002) |
| SQLAlchemy / `repository.py` | Kysely repositories (ADR 0002) |
| Pydantic | Zod (`schemas.ts`, `packages/contracts`) |
| arq / Celery / `jobs/runner.py` | BullMQ in `apps/worker` (ADR 0003) |
| pytest / Hypothesis | Vitest / fast-check |
| `backend/app/modules/<m>/` | `apps/api/src/modules/<m>/` |
| `frontend/src/...` | `apps/web`, `apps/field`, `apps/portal` or `packages/*` (ADR 0004) |
| `module.toml` / `manifest.yaml` | `manifest.json`, validated by Zod `ModuleManifest` |
| import-linter | dependency-cruiser + ESLint boundaries |
| WorkOS (identity module text) | Keycloak + in-app credentials (ADR 0005) |

## Consequences

Generated task files still contain the old names. Agents apply this table rather than stopping, and
rewrite a task file (marked `hand-edited`) when they pick it up.
