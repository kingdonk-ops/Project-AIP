# `make check` runs every backend and frontend gate (ARCH-01). CI runs the same commands.
.PHONY: check check-py check-ts check-docs check-boundaries install

install:
	uv sync --all-packages --frozen
	pnpm install --frozen-lockfile

check: check-py check-ts check-docs check-boundaries

# ARCH-03: module import boundaries (import-linter; run from the repo root so tools/ci is
# importable), manifest coverage and the ADR 0004 layout. ESLint boundaries run in check-ts.
check-boundaries:
	uv run lint-imports --no-cache
	python3 tools/ci/check_manifests.py
	python3 tools/ci/check_layout.py

check-py:
	uv run ruff check
	uv run ruff format --check
	uv run pyright
	uv run pytest
	uv run aip-db lint

check-ts:
	pnpm -r lint
	pnpm -r typecheck
	pnpm -r build
	pnpm -r test

# STACK-01: ADR record, errata marker and version pins; SECURITY-01: threat model and provenance log.
# Stdlib only (no uv/pnpm needed).
check-docs:
	python3 tools/ci/check_adrs.py
	python3 -m unittest tools/ci/test_check_adrs.py
	python3 tools/ci/check_security_docs.py
	python3 -m unittest tools/ci/test_check_security_docs.py
