# API and worker image (STACK-05): one image, two commands.
#   api:    uvicorn aip.main:create_app --factory --host 0.0.0.0 --port 8000
#   worker: procrastinate worker once OPS-02 lands (a stub until then; see infra/docker-compose.yml)
# Build from the repository root:
#   docker build -f apps/api/Dockerfile --build-arg GIT_SHA=$(git rev-parse HEAD) \
#     --build-arg BUILD_ID=local -t aip-api .
# GIT_SHA and BUILD_ID become image labels and env; GET /api/v1/platform/version reports them.

ARG PYTHON_IMAGE=python:3.12.15-slim-bookworm

FROM ${PYTHON_IMAGE} AS build

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /src

# Dependencies first (cached layer). The root pyproject.toml is the uv workspace root.
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
RUN uv sync --frozen --no-dev --package aip --no-install-workspace

# The package itself, installed non-editable so the runtime stage needs only /opt/venv.
# Tests are left out by .dockerignore.
COPY apps/api apps/api
RUN uv sync --frozen --no-dev --package aip --no-editable


FROM ${PYTHON_IMAGE} AS runtime

ARG GIT_SHA=unknown
ARG BUILD_ID=dev

LABEL org.opencontainers.image.title="aip-api" \
      org.opencontainers.image.source="https://github.com/kingdonk-ops/Project-AIP" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.version="${BUILD_ID}"

# curl is the container healthcheck (GET /api/v1/health/ready, OPS-04).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 aip \
    && useradd --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin aip

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AIP_ALEMBIC_CONFIG=/app/apps/api/alembic.ini \
    GIT_SHA="${GIT_SHA}" \
    BUILD_ID="${BUILD_ID}"

WORKDIR /app

COPY --from=build /opt/venv /opt/venv
# The readiness probe compares the database revision with this script directory's head.
COPY apps/api/alembic.ini apps/api/alembic.ini
COPY apps/api/migrations apps/api/migrations

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "aip.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
