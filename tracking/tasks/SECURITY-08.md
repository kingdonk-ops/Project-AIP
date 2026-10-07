# SECURITY-08 — Production strip test and security CI workflow

<!-- hand-edited: depends-on synced from BOARD.md -->

| Field | Value |
|---|---|
| Module | [`security`](../../docs/blueprint/modules/security/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-03, STACK-04 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/security/README.md`](../../docs/blueprint/modules/security/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Prove dev tooling is absent from production images and add the scanning gates.

- **files**:
  - backend/tests/security/test_prod_build_strip.py
  - .github/workflows/security.yml
  - Dockerfile
  - backend/app/modules/security/strip_manifest.txt
- **steps**:
  - 1. List the forbidden paths and modules: admin fixtures, architecture_map, module_builder, pipelines, the compliance DSL.
  - 2. In the Dockerfile use a multi-stage build that excludes them.
  - 3. The test builds the prod target and runs find and import checks inside the image.
  - 4. In security.yml add jobs: syft SBOM, pip-audit and npm audit, gitleaks, Trivy image scan failing on HIGH or CRITICAL, cosign signing.
  - 5. Add a vulnerability exception file with an expiry date per entry.
  - 6. Upload the SBOM and scan outputs as artefacts for evidence.
- **acceptance**:
  - Any forbidden path in the prod image fails the test.
  - A known HIGH CVE fails the Trivy job unless excepted.
  - A planted secret fails gitleaks.
- **tests**:
  - **e2e**:
    - The workflow runs on a PR and attaches the SBOM and signed image digest.
  - **integration**:
    - Prod image: 'import app.modules.module_builder' raises ImportError.
    - A dev image build fails the strip test (negative control).
    - A test file with a fake AWS key makes gitleaks exit non-zero.
  - **unit**:
    - Manifest parser returns the 5 forbidden entries.
