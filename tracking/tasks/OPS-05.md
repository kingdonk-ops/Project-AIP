# OPS-05 — Client error sink

<!-- hand-edited: depends-on synced from BOARD.md -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | OPS-04, PLAN-R1 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Accept scrubbed, rate-limited browser error reports as hostile input.

- **depends on**:
  - OPS-04
- **files**:
  - backend/app/modules/ops/client_errors.py
  - backend/tests/ops/test_client_errors.py
  - frontend/src/lib/reportError.ts
- **steps**:
  - 1. Add a Pydantic schema with strict max lengths: stack up to 8 KB, body up to 16 KB overall.
  - 2. Scrub query strings, tokens and form values from the URL and stack.
  - 3. Add rate limits of 30/min per IP and 300/min per tenant using Redis.
  - 4. Insert via an insert-only DB path and store hashes of tenant and project.
  - 5. Forward a sanitised line to the log stack.
  - 6. Add a frontend helper that never sends form values.
- **acceptance**:
  - An oversized body returns 413.
  - The 31st request in a minute from one IP returns 429.
  - Stored data contains no token or query string.
- **tests**:
  - **e2e**:
    - Trigger a thrown UI error: exactly one report is received with no PII.
  - **integration**:
    - POST 31 reports from one IP: the 31st returns 429.
    - Payload with '<script>' is stored escaped, and logs show escaped text.
    - The app role cannot UPDATE or DELETE client_error_reports.
  - **unit**:
    - Scrub of 'https://x/a?token=abc#z' returns 'https://x/a'.
    - A stack of 9 KB is rejected by the schema.
