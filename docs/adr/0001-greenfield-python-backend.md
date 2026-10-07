# ADR 0001: Greenfield build: Python backend, TypeScript frontends

- **Status:** accepted (owner, 2026-10-07: "You can use python instead of typescript, but I don't want to use the aip repository")
- **Date:** 2026-10-07 (revised; the first version chose a TypeScript backend)
- **Affects:** all modules and tasks

## Context

The owner first chose a TypeScript rebuild. The stack review ([08](../reviews/08-stack-decision.md))
recommended a Python backend with TypeScript frontends. The owner then allowed Python but ruled out reusing the
AIP codebase. So this is a **greenfield build**. Even without AIP reuse, Python still wins on three points:
- **Fit with existing decisions:** "Keep Alembic raw SQL" and the original job-queue choice are Python
  decisions, and much of the blueprint and many generated task specs are already Python-shaped.
- **Library fit:** PAdES signing (pyHanko), IFC (IfcOpenShell), OCR (OCRmyPDF) and image tooling are best in Python.
- **One backend language:** the API, workers and file-processing sandboxes all share it.

## Decision

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 Core (async) and Alembic (ADR 0002), plus Procrastinate
  for jobs (ADR 0003). Strict typing with pyright, and ruff for linting.
- **Frontends:** TypeScript and React, built with Vite (ADR 0004). They use a client generated from the API's OpenAPI spec.
- **AIP is not used.** No AIP code, schema or data is copied or read. The blueprint text is the only
  specification. "Port from AIP" in any doc means *implement the behaviour the blueprint describes*.
  Golden tests come from blueprint text and are confirmed by the owner.
  "Migrate Kaefer data from AIP" is an R1 data-import task, using an export the owner provides.
- **Shared rules:** JSONLogic runs server-side in Python and client-side in TS. Both run the same golden vectors
  in `packages/contracts/jsonlogic-vectors/`, and CI fails if they disagree.

| Doc text says | Use |
|---|---|
| NestJS / `apps/api/src/modules/<m>/*.ts` (hand-written specs before this revision) | `apps/api/aip/modules/<m>/*.py` (ADR 0004) |
| Kysely / node-pg-migrate | SQLAlchemy Core + Alembic raw-SQL revisions (ADR 0002) |
| Zod schemas in the API | Pydantic models (`schemas.py`); TS types generated from OpenAPI |
| BullMQ / arq / Celery | Procrastinate (ADR 0003) |
| Vitest / Testcontainers-node (backend) | pytest / testcontainers-python / Hypothesis |
| Next.js | Vite + React + TanStack Router (ADR 0004) |
| `services/sidecar` | sandboxed Python worker images in `apps/sandbox/` (ADR 0003) |
| WorkOS | Keycloak broker + in-app credentials (ADR 0005) |
| dependency-cruiser (backend) | import-linter contracts |

## Consequences

Backend task specs written in TypeScript are converted before they start. The board's notes column says which ones.
