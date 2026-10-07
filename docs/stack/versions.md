# Toolchain versions

One table for every pinned toolchain component (STACK-01). `tools/ci/check_adrs.py` fails CI when the
Python or Node row disagrees with `.python-version` / `.nvmrc`. Exact versions come from `uv.lock` and
`pnpm-lock.yaml` as committed by ARCH-01; a component marked *not yet added* is recorded with the line its
first task must use, and that task updates its row.

| Component | Version | Pinned in | Upgrade policy |
|---|---|---|---|
| Python | 3.12 | `.python-version`, `apps/api/pyproject.toml` `requires-python = ">=3.12"`, ruff `target-version`, pyright `pythonVersion` (CI also runs 3.13) | minor bumps by ADR |
| FastAPI | 0.142.2 | `uv.lock` (`fastapi>=0.115` in `apps/api/pyproject.toml`) | lockfile refresh in a dedicated PR; read the changelog for 0.x breaking changes |
| Pydantic | 2.13.5 | `uv.lock` (`pydantic>=2.9`) | stay on 2.x; major by ADR |
| Uvicorn | 0.54.0 | `uv.lock` (`uvicorn[standard]>=0.32`) | lockfile refresh |
| SQLAlchemy | 2.0.x (not yet added) | `uv.lock` once the first database task adds it (ADR 0002: Core, not ORM) | stay on 2.0.x; major by ADR |
| asyncpg | current stable (not yet added) | `uv.lock` once the first database task adds it | lockfile refresh |
| Alembic | 1.x (not yet added) | `uv.lock` once the first migration task adds it | stay on 1.x; major by ADR |
| Procrastinate | current stable major (not yet added) | `uv.lock` once the first jobs task adds it (ADR 0003) | major by ADR |
| PostgreSQL | 16 | `pgvector/pgvector:pg16` image in compose and Testcontainers (not yet added) | major by ADR with a migration rehearsal |
| ruff | 0.16.10 | `uv.lock` (dev group `ruff>=0.8`) | lockfile refresh; fix new lint findings in the same PR |
| pyright | 1.1.414 | `uv.lock` (dev group `pyright>=1.1.390`) | lockfile refresh |
| pytest | 9.1.1 | `uv.lock` (dev group `pytest>=8.3`) | lockfile refresh |
| Node | 22 | `.nvmrc`, root `package.json` `engines.node = ">=22 <23"`, CI `setup-node` | LTS majors only, by ADR |
| pnpm | 10.28.0 | root `package.json` `packageManager` | minor/patch freely; major by ADR |
| TypeScript | 6.0.3 | `pnpm-lock.yaml` (`~6.0.3`) | minor bumps in a dedicated PR |
| Vite | 8.3.3 | `pnpm-lock.yaml` (`^8.3.3`) | stay on the major; major by ADR 0004 update |
| React | 19.3.0 | `pnpm-lock.yaml` (`^19.3.0`) | stay on the major; major by ADR |
| TanStack Router | 1.170.41 | `pnpm-lock.yaml` (`@tanstack/react-router ^1.170.41`) | lockfile refresh |
| Vitest | 5.0.3 | `pnpm-lock.yaml` (`^5.0.3`) | stay on the major |
| Playwright | current stable (not yet added) | `pnpm-lock.yaml` once the first e2e task adds `@playwright/test` | lockfile refresh; browsers pinned by the same version |
