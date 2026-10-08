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
| SQLAlchemy | 2.0.54 | `uv.lock` (`sqlalchemy[asyncio]>=2.0,<2.1` in `apps/api/pyproject.toml`; ADR 0002: Core, not ORM) | stay on 2.0.x; major by ADR |
| asyncpg | 0.32.0 | `uv.lock` (`asyncpg>=0.30`) | lockfile refresh |
| Alembic | 1.20.0 | `uv.lock` (`alembic>=1.14,<2`; DATABASE-08) | stay on 1.x; major by ADR |
| structlog | 26.1.0 | `uv.lock` (`structlog>=26.1.0`; OPS-04 JSON logging) | lockfile refresh |
| redis-py | 8.1.0 | `uv.lock` (`redis>=8.1.0`; MIT client for the OPS-04 readiness `PING`) | lockfile refresh |
| OpenTelemetry SDK and OTLP/HTTP exporter | 1.45.1 | `uv.lock` (`opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http` `>=1.45.1`; OPS-04) | lockfile refresh; upgrade with the instrumentation packages |
| OpenTelemetry instrumentation (FastAPI, SQLAlchemy, Redis) | 0.66b1 | `uv.lock` (`opentelemetry-instrumentation-*` `>=0.66b1`; OPS-04) | upgrade together with the SDK |
| Procrastinate | current stable major (not yet added) | `uv.lock` once the first jobs task adds it (ADR 0003) | major by ADR |
| PostgreSQL | 16 | `pgvector/pgvector:pg16` image in CI (`ci.yml` `python` and `db` service containers) and the Testcontainers fixture (DATABASE-08); `pgvector/pgvector:0.8.7-pg16-bookworm` in `infra/docker-compose.yml` (STACK-05) | major by ADR with a migration rehearsal |
| Compose images (STACK-05) | Valkey 8.1.10 (BSD-3), RustFS 1.0.1 (Apache-2.0), Gotenberg 8.37.0 (MIT), Keycloak 26.7.5 (Apache-2.0), LocalStack 4.4.0 (Apache-2.0, `aws` profile), nginx-unprivileged 1.30.5 (BSD-2) | `infra/docker-compose.yml`, `apps/web/Dockerfile` (exact tags; `tools/tests/test_compose.py` rejects floating tags and the Redis server image) | bump one image per PR after its release notes; Keycloak within the 14-day patch window (ADR 0005) |
| Base images (STACK-05) | `python:3.12.15-slim-bookworm`, `node:22.23.3-bookworm-slim` | `apps/api/Dockerfile`, `apps/sandbox/Dockerfile`, `apps/web/Dockerfile` | patch bumps freely; minor with the Python/Node rows |
| Testcontainers (Python) | 4.15.0 | `uv.lock` (dev group `testcontainers[postgres,redis]>=4.8` in `apps/api/pyproject.toml`; OPS-04 Redis tests use `valkey/valkey:8-alpine`, BSD-3) | lockfile refresh |
| uv (migrator and API images) | 0.11.32 | `infra/docker/migrator.Dockerfile`, `apps/api/Dockerfile` (`ghcr.io/astral-sh/uv:0.11.32`) | bump with the local uv |
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
| cyclonedx-bom (`cyclonedx-py`) | 7.5.0 | `tools/sbom.sh` `CYCLONEDX_BOM_VERSION` (run with `uvx`; Apache-2.0) | bump in a dedicated PR; re-run `make sbom` |
| cdxgen | 12.8.5 | `tools/sbom.sh` `CDXGEN_VERSION` (run with `npx`; Apache-2.0) | bump in a dedicated PR; re-run `make sbom` |
| syft | 1.33.0 | `.github/workflows/release.yml` `SYFT_VERSION` (Apache-2.0) | bump in a dedicated PR |
