# STACK-04 — Licence allow-list and CycloneDX SBOM in CI

| Field | Value |
|---|---|
| Module | [`stack`](../../docs/blueprint/modules/stack/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | ARCH-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/stack/README.md`](../../docs/blueprint/modules/stack/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Block GPL/AGPL dependencies in shipped images and produce an SBOM for each release.

- **depends on**:
  - ARCH-01
- **files**:
  - tools/sbom.sh
  - config/licence-policy.json
  - tools/ci/check-licences.ts
  - .github/workflows/release.yml
- **steps**:
  - 1. Generate the JS SBOM with cyclonedx-npm and the Python sidecar SBOM with cyclonedx-py.
  - 2. Define allow and deny lists in licence-policy.json, plus an exceptions list with an expiry date and an approver.
  - 3. check-licences reads the SBOMs and fails on any denied licence that has no unexpired exception.
  - 4. Upload the SBOMs as release artefacts.
  - 5. Emit security.sbom.policy_violation when the check fails.
- **acceptance**:
  - An AGPL-3.0 dependency fails the build.
  - An expired exception fails the build.
  - An SBOM is attached to every release.
- **tests**:
  - **e2e**:
    - Run the release workflow on a test tag. Expected: the CycloneDX JSON artefacts are attached and the job is green.
  - **integration**:
    - Run check-licences on a fixture SBOM with one AGPL component. Expected: exit 1 and the output names the component.
    - Run it with a valid exception expiring in 30 days. Expected: exit 0 with a warning.
  - **unit**:
    - The licence classifier maps 'AGPL-3.0-only' to deny and 'MIT' to allow.
    - An exception with expires=yesterday is ignored.
