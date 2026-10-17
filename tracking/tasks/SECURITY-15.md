# SECURITY-15 — Gate the Coolify deploy on the security scans

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | OPS-11, SECURITY-08 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. ADRs: 0011
4. [review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md), the finding named below

## Background

[review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md) finding **M6**. `deploy-coolify.yml:41-62` builds, pushes and deploys on every push to main without
depending on `security.yml`. The keycloak, postgres and migrator demo images are never Trivy-scanned or SBOM'd.
Lines 118-120 pin actions by tag (`security.yml` pins by SHA). Cosign signs local image ids and falls back to an
ephemeral key (`security.yml:173-179`).

## Spec

Nothing reaches the internet-facing demo unscanned or unsigned.

- **files**:
  - .github/workflows/deploy-coolify.yml
  - .github/workflows/security.yml
- **steps**:
  - 1. Gate the deploy on the security jobs (same workflow or `workflow_run`).
  - 2. Scan and SBOM all five demo images.
  - 3. SHA-pin the deploy workflow's actions.
  - 4. Sign the pushed registry digests, not local ids.
  - 5. Fail on `main` when `COSIGN_PRIVATE_KEY` is missing (owner adds the secret, review O2).
- **acceptance**:
  - A failing scan stops the deploy.
  - All five images have a Trivy result and an SBOM.
  - `cosign verify` passes on the pushed digests.
- **tests**:
  - **integration**:
    - workflow lint (actionlint) → every `uses:` is SHA-pinned
    - a dry run with a seeded critical vuln → the deploy job does not run
