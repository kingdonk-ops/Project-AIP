# SECURITY-01 — Threat model and AGPL provenance log

| Field | Value |
|---|---|
| Module | [`security`](../../docs/blueprint/modules/security/README.md) |
| Phase | P0 |
| Size | XS |
| Depends on | — |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/security/README.md`](../../docs/blueprint/modules/security/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Record the threat model and clean-room provenance before schema design.

- **files**:
  - docs/security/threat-model.md
  - docs/security/provenance-log.md
  - backend/tests/security/test_docs_present.py
- **steps**:
  - 1. Write threat-model.md with sections for field PIN/magic link, portal, inbound email/webhooks, legal records and AI. Each section lists assets, threats (STRIDE), controls and residual risk.
  - 2. Write provenance-log.md with a table: date, reference area, who viewed it, statement of no copied code or schema, reviewer.
  - 3. Add an entry for each OpenConstructionERP feature area used as a reference.
  - 4. Add a note that legal advice on AGPL status is pending, with a placeholder reference.
  - 5. Add a test asserting both files exist and contain the required headings.
- **acceptance**:
  - Both docs are in the repo.
  - The test fails if any of the five threat areas is missing.
- **tests**:
  - **e2e**:
    - CI docs job passes on main.
  - **integration**:
    - Remove the 'AI' heading in a temp copy: the test fails naming it.
  - **unit**:
    - The heading parser finds 5 required threat headings in the file.
