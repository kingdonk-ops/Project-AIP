# STACK-04 — Licence allow-list and CycloneDX SBOM in CI
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

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
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) (Python backend, TS frontends), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (sandbox images ship native tools), [0004](../../docs/adr/0004-repository-layout.md) (`config/licence-policy.json`)

## Spec

Block GPL/AGPL dependencies in shipped artefacts (Python API/worker, sandbox images, web bundles) and attach CycloneDX SBOMs to every release.

- **depends on**:
  - ARCH-01
- **files**:
  - tools/sbom.sh
  - config/licence-policy.json
  - tools/ci/check_licences.py
  - tools/ci/tests/test_check_licences.py
  - tools/ci/tests/fixtures/ (`sbom_agpl.json`, `sbom_clean.json`, `policy_with_exception.json`)
  - .github/workflows/release.yml
- **steps**:
  - 1. `tools/sbom.sh` writes to `dist/sbom/`: the Python SBOM from `uv export --frozen --no-dev --format requirements-txt | cyclonedx-py requirements -` (`python.cdx.json`); the JS SBOM for the pnpm workspace with `cdxgen -t pnpm` (`js.cdx.json`; `cyclonedx-npm` does not read pnpm lockfiles); and, when images are built, one SBOM per container image (`apps/api` image and each `apps/sandbox` image) with `syft <image> -o cyclonedx-json` (`image-<name>.cdx.json`), which covers OS packages such as Ghostscript.
    - *Implementation note (2026-10-07):* `cyclonedx-py requirements` reads no licence metadata, so every component came out unknown. `tools/sbom.sh` installs the same `uv export --frozen --no-dev` requirements into a throwaway venv and runs `cyclonedx-py environment` on it. Policy details the spec leaves open (image OS packages, extra permissive licences) are in ADR 0011.
  - 2. `config/licence-policy.json`: `allow` (e.g. MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, ISC, PSF-2.0, MPL-2.0), `deny` (GPL-*, AGPL-*, SSPL-1.0, and unknown/no licence), `review` (LGPL-*, allowed only in components whose SBOM path is a sandbox image), and `exceptions` entries `{component, licence, reason, approver, expires}`.
  - 3. `tools/ci/check_licences.py <sbom...>` classifies every component's SPDX id or expression (an `OR` expression passes if any branch is allowed; `AND` needs all), and exits 1 on any denied component without an unexpired exception, printing `component@version licence source-sbom`. Exceptions expiring within 30 days pass with a warning.
  - 4. In `release.yml` (on tag `v*`), build images, run `tools/sbom.sh` and `check_licences.py`, and upload `dist/sbom/*.cdx.json` as release assets.
  - 5. On failure, print one JSON line `{"event": "security.sbom.policy_violation", "component": ..., "licence": ..., "sbom": ...}` per violation and a GitHub `::error` annotation (CI has no tenant outbox; the security module ingests these later).
- **acceptance**:
  - An AGPL-3.0 dependency fails the build.
  - An expired exception fails the build.
  - An SBOM is attached to every release.
- **tests**:
  - **unit**:
    - The classifier maps `AGPL-3.0-only` to deny, `MIT` to allow, `LGPL-3.0-or-later` to review, and `MIT OR GPL-3.0-only` to allow.
    - An exception with `expires` = yesterday is ignored.
  - **integration**:
    - `check_licences.py tools/ci/tests/fixtures/sbom_agpl.json` (one component `fixture-agpl@1.0.0`, `AGPL-3.0-only`). Expected: exit 1 and the output names `fixture-agpl@1.0.0`.
    - Same SBOM with `policy_with_exception.json` (exception expiring in 30 days). Expected: exit 0 with a warning naming the exception.
    - `check_licences.py sbom_clean.json`. Expected: exit 0, no output lines.
  - **e2e**:
    - Run the release workflow on a test tag `v0.0.0-sbomtest`. Expected: `python.cdx.json`, `js.cdx.json` and the image SBOMs are attached and the job is green.
