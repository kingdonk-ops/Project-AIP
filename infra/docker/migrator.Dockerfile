# Migrator image (DATABASE-08): one-shot `aip-db migrate` as aip_owner (ECS task in AWS; a compose
# service the API waits on with `condition: service_completed_successfully`).
# Build from the repository root:
#   docker build -f infra/docker/migrator.Dockerfile -t aip-migrator .
#   docker run --rm -e DATABASE_MIGRATOR_URL=postgresql://aip_owner:...@db:5432/aip aip-migrator
FROM python:3.12.15-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    AIP_ALEMBIC_INI=/app/apps/api/alembic.ini \
    AIP_REPO_ROOT=/app

WORKDIR /app

# Dependencies first (cached layer). The root pyproject.toml is the uv workspace root.
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
RUN uv sync --frozen --no-dev --package aip --no-install-workspace

# Only the parts of the `aip` package the migrator imports, plus Alembic config and revisions.
COPY apps/api/aip/__init__.py apps/api/aip/__init__.py
COPY apps/api/aip/platform/__init__.py apps/api/aip/platform/__init__.py
COPY apps/api/aip/platform/db apps/api/aip/platform/db
COPY apps/api/alembic.ini apps/api/alembic.ini
COPY apps/api/migrations apps/api/migrations
COPY db db
RUN uv sync --frozen --no-dev --package aip --no-editable \
    && useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin aip

USER 10001

ENTRYPOINT ["aip-db"]
CMD ["migrate"]
