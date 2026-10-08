# SECURITY-08 — Production strip test and security CI workflow

<!-- hand-edited: depends-on synced from BOARD.md; converted to the Python backend per ADR 0001 (2026-10-08) -->

## Conversion to the real stack (ADR 0001, 0004, 0012)

The spec below predates ADR 0001. Built as follows (Python 3.12 + FastAPI in the uv workspace,
Vite TS apps in the pnpm workspace):

| Spec says | Built as |
|---|---|
| `backend/app/modules/security/strip_manifest.txt` | `config/prod-strip-manifest.txt` (no `security` API module exists yet; the manifest is CI policy like `config/licence-policy.json`) |
| manifest parser | `tools/ci/check_prod_strip.py` (stdlib; also runs inside the image from stdin), unit tests `tools/ci/tests/test_check_prod_strip.py` |
| `backend/tests/security/test_prod_build_strip.py` | `apps/api/tests/security/test_prod_build_strip.py` (pytest; image tests run when `AIP_TEST_*_IMAGE`/`_DIST` are set, which `security.yml` does and fails on any skip) |
| `Dockerfile` | `apps/api/Dockerfile` (already multi-stage from STACK-05): strip check in the `build` stage, `dev` target as the negative control, `AIP_ENV=production` default; `.dockerignore` drops `aip/modules/_template` |
| forbidden "paths and modules" | `aip.fixtures.admin`, `aip.modules.architecture_map`, `aip.modules.module_builder`, `aip.modules.pipelines`, `aip.modules.compliance_dsl`; plus dev modules (pytest, testcontainers, `_template`, `widgets`, ...), test files, image paths and the `/api/v1/_debug` route (OPS-04/ARCH-04 test-only route) |
| web build (not in the spec) | the same checker on `apps/web/dist` and the `aip-web` image: no source maps, no React dev runtime (`jsxDEV`), no Vite client/HMR; a `NODE_ENV=development` build is the negative control |
| npm audit | `pnpm audit --json` gated by `tools/ci/check_vuln_exceptions.py --pnpm-audit` (pnpm's `--ignore` persists IDs with no expiry) |
| pip-audit | `uvx pip-audit` on `uv export --no-dev` (hashes required) |
| syft SBOM | syft CycloneDX SBOMs of the API and web images (STACK-04 still owns the dependency SBOMs and licence policy) |
| gitleaks | the gitleaks CLI image over the full history (`gitleaks-action` needs a licence key for organisations) |
| Trivy, failing on HIGH/CRITICAL | Trivy image scan, `--ignore-unfixed` (fixable HIGH/CRITICAL fail), with known-HIGH, exception and expired-exception controls on a generated Django 2.2.0 fixture |
| cosign signing | key-based `cosign sign-blob` over the image digests and SBOMs, no public log (private repo); ephemeral key until the owner adds `COSIGN_PRIVATE_KEY`/`COSIGN_PASSWORD`; registry signatures come with OPS-09 |
| vulnerability exception file | `config/vuln-exceptions.txt` (Trivy ignore format, `# why:` + `exp:` ≤ 180 days), checked in `make check` |
| also bandit (not in the spec) | `uvx bandit` on `apps/api/aip`, medium severity/confidence and up |

Tool licences (no paid account needed): Trivy Apache-2.0, syft Apache-2.0, cosign Apache-2.0,
gitleaks MIT, pip-audit Apache-2.0, bandit Apache-2.0, pnpm MIT. Semgrep was not used: its
community rules are not under a permissive licence. Details: ADR 0012.

Folded in from the STACK-05 security review: `ci.yml` top-level `permissions: contents: read`;
`infra/docker/migrator.Dockerfile` pinned to `python:3.12.15-slim-bookworm`.

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
