# `make check` runs every backend and frontend gate (ARCH-01). CI runs the same commands.
.PHONY: check check-py check-ts install

install:
	uv sync --all-packages --frozen
	pnpm install --frozen-lockfile

check: check-py check-ts

check-py:
	uv run ruff check
	uv run ruff format --check
	uv run pyright
	uv run pytest

check-ts:
	pnpm -r lint
	pnpm -r typecheck
	pnpm -r build
	pnpm -r test
