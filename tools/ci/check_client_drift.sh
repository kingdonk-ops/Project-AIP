#!/usr/bin/env bash
# STACK-03: fail when the committed API client is out of date with the FastAPI schema.
# Re-exports openapi.json, regenerates the client and diffs packages/api-client. On drift it
# prints the diff and exits 1; fix it by running the same two commands and committing the result.
#
# AIP_PYTHON overrides the interpreter (default `uv run python`).
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

read -r -a python <<<"${AIP_PYTHON:-uv run python}"
"${python[@]}" tools/codegen/export_openapi.py
pnpm --filter api-client generate

if ! git diff --exit-code -- packages/api-client; then
  echo "::error::packages/api-client is out of date with the API schema." >&2
  echo "Run: uv run python tools/codegen/export_openapi.py && pnpm --filter api-client generate" >&2
  exit 1
fi
untracked=$(git ls-files --others --exclude-standard -- packages/api-client)
if [ -n "$untracked" ]; then
  echo "$untracked"
  echo "::error::packages/api-client has new generated files that are not committed." >&2
  exit 1
fi
echo "ok: packages/api-client matches the API schema"
