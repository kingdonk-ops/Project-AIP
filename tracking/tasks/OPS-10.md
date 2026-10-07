# OPS-10 — Cosign signing, prod promotion approval, digest rollback

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | OPS-09 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. ADRs: 0004 (`infra/`), 0007 (AIP stays live until R1; production here is the new platform's production)
4. Only if the step needs it: [`tracking/tasks/OPS-09.md`](OPS-09.md) for the workflow and deploy scripts this task extends

## Spec

Finish the supply-chain path. Sign every scanned digest with cosign (keyless, using the GitHub OIDC identity), verify the signature before any deploy, promote the same staging digest to production only after a manual approval, and roll back automatically to the last known-good digest when post-deploy smoke fails.

- **files**:
  - .github/workflows/build-promote.yml
  - infra/deploy/verify-signature.sh
  - infra/deploy/last-good.ts
  - infra/deploy/rollback.ts
  - infra/deploy/tests/
  - infra/terraform/envs/production/main.tf
  - infra/terraform/modules/ci-oidc/main.tf (add the production role)
- **steps**:
  - 1. Add a `sign` job after `scan`: `cosign sign --yes <repo>@<digest>` for each app, keyless through GitHub OIDC and Sigstore. Attach the CycloneDX SBOM from STACK-04 as an attestation (`cosign attest --type cyclonedx`). The job needs `id-token: write`; all others keep it off.
  - 2. In verify-signature.sh, run `cosign verify` with `--certificate-identity-regexp '^https://github.com/<org>/<repo>/.github/workflows/build-promote.yml@refs/heads/main$'` and `--certificate-oidc-issuer https://token.actions.githubusercontent.com`. Every deploy step (staging and production) calls it first and aborts on failure. An unsigned image, or one signed from another workflow or branch, never deploys.
  - 3. In last-good.ts, after a successful staging or production smoke, write the digests to SSM Parameter Store at `/aip/<env>/last-good-digests` as JSON `{api, worker, web, sha, at}`. Before deploy, read the current value as the rollback target.
  - 4. Add a `promote-production` job, `needs: deploy-staging`, using GitHub environment `production` with required reviewers (at least 1, not the commit author) and a branch rule limited to main. It does not build: it downloads `digests.json` from the same run, verifies the signatures, runs migrations against production with the OPS-09 script, deploys by digest and smokes. For the record (SOC 2 change log), it writes a summary to the job summary: approver, digests, SHA and migration list.
  - 5. In rollback.ts, when post-deploy smoke fails in either environment, re-register the task definition pointing at the last-good digests, update the services, wait until they are stable, re-run the smoke, and fail the workflow with "rolled back to <sha>". Migrations are forward-only (ADR 0002), so rollback redeploys code only. Document in the script header that every migration must be backward-compatible with the previous release (expand/contract). Also enable the ECS deployment circuit breaker with `rollback = true` in the service module as a second layer.
  - 6. In envs/production/main.tf, compose the OPS-07 modules for production (ap-southeast-2) with production sizes, deletion protection on RDS, and the ECR repos shared from staging (or replicated). Add the production CI role trusted only for environment `production`. Applying production infra needs the owner's AWS account: make the plan clean and leave the apply as a manual step in the PR.
- **acceptance**:
  - Every deployed digest has a verifiable cosign signature and SBOM attestation from this repository's main-branch workflow.
  - Production receives exactly the digest that passed staging, only after a named reviewer approves. Nothing is rebuilt.
  - A failed smoke after deploy restores the previous digest automatically, and the workflow reports it.
  - The production OIDC role cannot be assumed from the staging environment or from a PR.
- **tests**:
  - **unit**:
    - rollback with last-good `{api:'sha256:aaa'}` and current `sha256:bbb` produces an update with image `…@sha256:aaa`. With no last-good value it exits 1 with "no rollback target" and does not touch the services.
    - last-good writes JSON containing all three digests and the SHA. A missing digest throws before any write.
    - verify-signature.sh with a mocked `cosign` exiting 1 exits 1 and prints the image reference.
  - **integration**:
    - Push a locally built, unsigned image to the staging ECR and dispatch the deploy with it. Expected: the verify step fails and the service keeps its old task definition.
    - In staging, deploy a digest whose `/health/ready` returns 503 (env flag `FORCE_UNREADY=1`). Expected: the smoke fails, rollback runs, the service returns to the last-good digest, and the workflow ends red with "rolled back to <sha>".
    - `tofu plan` for envs/production is clean, and the plan shows RDS `deletion_protection = true`.
  - **e2e**:
    - Merge to main, let staging pass, and have a second team member approve `production`. Expected: production `/api/v1/platform/version` returns the same commit as staging, and `cosign verify` on the production task's image digest succeeds from a laptop.
