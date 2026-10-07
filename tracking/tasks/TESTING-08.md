# TESTING-08 — CI gates, k6 load script and mobile smoke job

| Field | Value |
|---|---|
| Module | [`testing`](../../docs/blueprint/modules/testing/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | TESTING-02, TESTING-04, TESTING-05, TESTING-06 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/testing/README.md`](../../docs/blueprint/modules/testing/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Define required promotion gates and the load and device suites.

- **depends on**:
  - TESTING-02
  - TESTING-04
  - TESTING-05
  - TESTING-06
- **files**:
  - .github/workflows/ci.yml
  - load/k6/morning_sync.js
  - load/k6/report_pack.js
  - e2e/playwright.config.ts
  - backend/pyproject.toml
- **steps**:
  - 1. In ci.yml add jobs: lint, unit with coverage --cov-fail-under=80 on domain and policy packages, integration, tenancy-gate, matrix-gate, migration, e2e.
  - 2. Make the gate job required for promotion.
  - 3. Write morning_sync.js: ramp to 5,000 virtual users over 5 minutes, each running pull then push, with thresholds p95 < 800ms and error rate < 1%.
  - 4. Write report_pack.js to enqueue a large pack and poll the job.
  - 5. Add Playwright projects for mobile Chrome (Pixel 5) and iPad.
  - 6. Make the k6 job manual or scheduled, not per PR.
- **acceptance**:
  - Failing a tenancy or matrix test blocks promotion.
  - The k6 script fails when a threshold is exceeded.
  - Mobile projects run the field PIN and offline journeys.
- **tests**:
  - **e2e**:
    - Playwright field PIN login journey passes on both the mobile Chrome and iPad projects.
  - **integration**:
    - Dry-run k6 with 5 VUs against staging: thresholds evaluated and summary JSON written.
  - **unit**:
    - Coverage config excludes UI and includes app/modules/*/domain and policies.
