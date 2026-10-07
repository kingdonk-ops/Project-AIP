# STACK-01 — Stack ADRs and reconciliation record

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
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Write one coherent decision record that resolves the conflicts between the scope document, the owner's decisions and the running AIP.

- **files**:
  - docs/adr/0001-modular-monolith.md
  - docs/adr/0002-stack-decision.md
  - docs/adr/0003-capability-library-choices.md
  - docs/adr/0004-agpl-clean-room.md
  - docs/adr/README.md
- **steps**:
  - 1. Rewrite 0002 to record the TypeScript rebuild (Node 22, NestJS, Next.js), superseding the earlier continue-AIP direction. Include the consequences and revisit triggers, including parity with AIP's 48 phases.
  - 2. Record the reconciliation: Alembic raw-SQL migrations stay as the sole schema authority and run from a standalone migration container. Drizzle is used as a query builder only and never generates migrations.
  - 3. Record the queue position as an open item for owner confirmation. BullMQ on Redis is the TypeScript default, arq runs the Python sidecar jobs, and Celery is not used.
  - 4. Write 0003 with one chosen library per capability: Gotenberg, PDF.js with Konva, Keycloak, JSONLogic, Dexie, S3 and RustFS.
  - 5. Write 0004 covering AGPL reference-only status, the clean-room rules and the provenance log location.
  - 6. Add front-matter (number, status, supersedes, decided_at) to each ADR.
- **acceptance**:
  - Every owner decision in the brief maps to exactly one ADR line.
  - No ADR remains that says 'continue AIP'.
  - The queue question is explicitly marked as awaiting owner confirmation.
- **tests**:
  - **e2e**:
    - CI docs job runs the ADR lint on a PR. Expected: green with the committed ADRs, red with a deliberately duplicated number.
  - **integration**:
    - The lint script fails when two ADRs share a number or a supersedes target does not exist.
    - The lint script passes on the committed ADR set.
  - **unit**:
    - Front-matter parser returns number, status and supersedes for each ADR file.
