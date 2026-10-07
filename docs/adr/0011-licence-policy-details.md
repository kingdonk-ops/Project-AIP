# ADR 0011: Licence policy details for the CI check (allow-list additions, image OS packages)

- **Status:** proposed
- **Date:** 2026-10-07
- **Affects:** STACK-04 (`config/licence-policy.json`, `tools/ci/check_licences.py`), SECURITY-08, apps/sandbox images

## Context

ADR 0009 allows MIT, BSD, Apache-2.0, ISC, PSF and MPL-2.0, sends LGPL to review and denies GPL, AGPL,
SSPL and anything needing a paid licence. It says any dependency outside the allow-list needs an ADR.
Running the STACK-04 check against the real SBOMs showed three gaps:

1. Today's dependency tree already uses other permissive licences: `isbot` (Unlicense, a runtime
   dependency of TanStack Router), `minimatch` (BlueOak-1.0.0), `caniuse-lite` (CC-BY-4.0, browser
   data), `chardet` (0BSD) and `defusedxml` (Python-2.0) in the SBOM tooling.
2. Every Linux base image ships GPL/LGPL operating-system packages (bash, coreutils, glibc). In
   `python:3.12-slim` almost all of the 88 Debian packages list a GPL licence. Applying the
   application allow-list to them would fail every image, including the planned sandbox images.
3. syft reports no licence for crates and Go modules compiled into third-party binaries (522 crates
   inside `uv` in the migrator image), so they would all be "unknown".

## Decision

- **Allow-list additions** (all permissive, no copyleft, no fee): MIT-0, 0BSD, Python-2.0, Zlib,
  PostgreSQL, Unlicense, CC0-1.0, BlueOak-1.0.0 and CC-BY-4.0 (data files only, e.g. caniuse-lite).
- **Also denied** besides GPL-*, AGPL-*, SSPL-*: BUSL-*, Elastic-*, Commons-Clause, CC-BY-NC-*,
  CC-BY-SA-*. A missing or unrecognised licence is denied.
- **Language dependencies** (pypi, npm and other library purls) in every SBOM get the full policy.
  LGPL passes only in sandbox image SBOMs (`image-sandbox-*.cdx.json`), as STACK-04 specifies.
- **Image system components** (deb/apk/rpm/alpm packages, `pkg:generic` and no-purl binaries, and
  cargo/golang modules compiled into third-party binaries) are mere aggregation: they ship unmodified
  and our code does not link them. For these only AGPL-*, SSPL-* and a named denylist (Ghostscript,
  libgs, MuPDF, PyMuPDF, OCRmyPDF) are denied. The named denylist applies to every SBOM.
- Several licence entries on one component must all pass (conservative AND), because CycloneDX does
  not say whether a list means AND or OR. Use an SPDX `OR` expression for a real dual licence.
- Our own packages (`aip`, `@aip/*`) are skipped.

## Consequences

- Images can be built on Debian slim bases, and Ghostscript still cannot get in (ADR 0009).
- Adding a licence to `allow` or a name to `first_party` still needs an ADR amendment. A one-off
  needs an `exceptions` entry with an approver and an expiry date.
- The owner should confirm the aggregation rule for base-image packages. If it is rejected, images
  need a distroless or scratch base, and this ADR must be superseded.
