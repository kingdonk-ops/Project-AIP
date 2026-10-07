#!/usr/bin/env bash
# Write CycloneDX SBOMs for every shipped artefact into dist/sbom/ (STACK-04).
#
# Usage: tools/sbom.sh [NAME=IMAGE_REF ...]
#   python.cdx.json      Python API/worker runtime dependencies (uv.lock, no dev group)
#   js.cdx.json          the pnpm workspace (web, field, portal and shared packages)
#   image-NAME.cdx.json  one per NAME=IMAGE_REF argument, OS packages included (needs syft);
#                        name sandbox images `sandbox-<worker>` so LGPL review applies to them.
# Then: python3 tools/ci/check_licences.py dist/sbom/*.cdx.json
#
# Tools (all Apache-2.0): cyclonedx-py (cyclonedx-bom, via uvx), cdxgen (via npx), syft.
# The Python SBOM is built from an environment installed from `uv export --frozen --no-dev`:
# `cyclonedx-py requirements` reads no licence metadata, so every component would be unknown.
set -euo pipefail

CYCLONEDX_BOM_VERSION="7.5.0"
CDXGEN_VERSION="12.8.5"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${SBOM_OUT:-$ROOT/dist/sbom}"
mkdir -p "$OUT"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "sbom: Python runtime dependencies -> $OUT/python.cdx.json"
uv export --project "$ROOT" --frozen --no-dev --all-packages --no-emit-workspace \
  --no-header --format requirements-txt -o "$WORK/requirements.txt" >/dev/null
uv venv --quiet --project "$ROOT" "$WORK/venv"
uv pip install --quiet --python "$WORK/venv/bin/python" --no-deps --require-hashes \
  -r "$WORK/requirements.txt"
uvx --from "cyclonedx-bom==$CYCLONEDX_BOM_VERSION" cyclonedx-py environment \
  --pyproject "$ROOT/apps/api/pyproject.toml" --spec-version 1.6 --output-reproducible \
  -o "$OUT/python.cdx.json" "$WORK/venv/bin/python"

echo "sbom: pnpm workspace -> $OUT/js.cdx.json"
# cyclonedx-npm does not read pnpm lockfiles. FETCH_LICENSE fills licences from the registry.
FETCH_LICENSE=true npx --yes "@cyclonedx/cdxgen@$CDXGEN_VERSION" -t pnpm --no-install-deps \
  --spec-version 1.6 -o "$OUT/js.cdx.json" "$ROOT" >"$WORK/cdxgen.log" 2>&1 \
  || { cat "$WORK/cdxgen.log"; exit 1; }
test -s "$OUT/js.cdx.json"

for spec in "$@"; do
  name="${spec%%=*}"
  ref="${spec#*=}"
  if [[ -z "$name" || "$name" == "$spec" || -z "$ref" ]]; then
    echo "sbom: expected NAME=IMAGE_REF, got '$spec'" >&2
    exit 2
  fi
  command -v syft >/dev/null || { echo "sbom: syft is not on PATH" >&2; exit 2; }
  echo "sbom: image $ref -> $OUT/image-$name.cdx.json"
  syft scan "$ref" -q -o "cyclonedx-json=$OUT/image-$name.cdx.json"
done

ls -1 "$OUT"/*.cdx.json
