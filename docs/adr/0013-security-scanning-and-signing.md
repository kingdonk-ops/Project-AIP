# ADR 0013: Security CI scanners, vulnerability exceptions and image signing

- **Status:** proposed
- **Date:** 2026-10-08
- **Affects:** security, ops; SECURITY-08, OPS-09

## Context

SECURITY-08 asks for a production strip test and CI gates: SBOM, dependency audit, secret
scanning, a Trivy image scan that fails on HIGH or CRITICAL unless excepted, and cosign signing.
ADR 0009/0011 allow only permissively licensed tools, and the owner wants nothing that needs a
paid account. The repository is private.

## Decision

- **Tools** (licence; all free, none needs an account):
  Trivy (Apache-2.0) image and fixture scans; syft (Apache-2.0) image SBOMs; cosign (Apache-2.0)
  signatures; gitleaks (MIT) run as the CLI image, not `gitleaks-action`, which needs a licence
  key for organisations; pip-audit (Apache-2.0) for Python runtime dependencies; pnpm audit (pnpm,
  MIT) for the JS workspace; bandit (Apache-2.0) for Python SAST. Semgrep is not used: its
  community rules are under the Semgrep Rules License, which is not a permissive open-source licence.
- **Pinning:** scanner images by tag and digest, third-party actions by commit SHA, Python tools
  by exact version through `uvx`, so they never enter `uv.lock` or the shipped SBOMs.
- **Gate:** Trivy fails on HIGH/CRITICAL findings that have a fixed version (`--ignore-unfixed`;
  unfixed OS findings are tracked through the evidence reports, not blocked). pnpm audit fails on
  HIGH/CRITICAL. bandit fails on medium severity with medium confidence and above.
- **Exceptions:** one file, `config/vuln-exceptions.txt`, in Trivy's ignore format. Every entry
  has a `# why:` line and an `exp:` date at most 180 days ahead. `tools/ci/check_vuln_exceptions.py`
  validates it in `make check` and feeds the IDs to pip-audit and the pnpm audit gate. pnpm's own
  `--ignore` is not used, because it writes the ID into `pnpm-workspace.yaml` with no expiry.
- **Signing:** key-based cosign `sign-blob` over the image digests and SBOMs, with no
  transparency-log upload. Keyless signing would publish the private repository's name and
  workflow in the public Fulcio and Rekor logs. The key lives in the `COSIGN_PRIVATE_KEY` and
  `COSIGN_PASSWORD` repository secrets. Until the owner adds them, CI signs with an ephemeral key,
  which proves only that the pipeline works. Registry signatures (`cosign sign` on a pushed
  digest) come with OPS-09, once images are pushed to ECR.
- **Strip test:** `config/prod-strip-manifest.txt` is the single list of what must not ship.
  `tools/ci/check_prod_strip.py` checks it inside the API image (imports, files, image paths, and
  routes under the image's `AIP_ENV` and `production`) and in the web build. The API Dockerfile
  runs the same check in its build stage. Its `dev` target is the negative control.

## Consequences

- A new HIGH CVE with a fix turns `security` red until the dependency is upgraded or an exception
  with an expiry is added. Expired exceptions fail `make check` and every scan.
- The owner must create the cosign key pair (`cosign generate-key-pair`) and add the two secrets
  for signatures to carry trust.
- New dev-only code (fixtures, generators, test routes) must be added to the strip manifest.
  Modules named after a forbidden entry cannot ship.
