# apps/api

Python package `aip`: FastAPI app, platform services and business modules (ADR 0001, 0004).

```bash
uv sync --all-packages --frozen
uv run uvicorn aip.main:create_app --factory --reload
uv run pytest
python tools/new_module.py <snake_case_name>   # scaffold a module from aip/modules/_template
```

## Database migrations (DATABASE-08, ADR 0002)

Forward-only Alembic revisions written as raw SQL live in `migrations/versions/`. Bootstrap a cluster once
as a superuser with `db/bootstrap/00_cluster.sql`, then run everything as `aip_owner`:

```bash
export DATABASE_MIGRATOR_URL=postgresql://aip_owner:...@localhost:5432/aip   # direct, never PgBouncer
uv run aip-db migrate        # alembic upgrade head (there is no downgrade)
uv run aip-db new add_widgets  # blank revision from migrations/script.py.mako
uv run aip-db lint           # filename, forward-only, raw SQL only, contract comments, one head, immutability
uv run aip-db snapshot       # rewrite db/schema.snapshot.sql (commit it)
uv run aip-db check-schema   # migrated schema vs the declared SQLAlchemy Core tables
```

## Health, logging and tracing (OPS-04)

| Variable | Used by | Default |
|---|---|---|
| `DATABASE_URL` | `GET /api/v1/health/ready` `db` and `migrations` checks (`select 1` as `aip_app`) | unset: check fails |
| `REDIS_URL` | `ready` `redis` check (`PING`) | unset: check fails |
| `AIP_ALEMBIC_CONFIG` | `ready` `migrations` check: the `alembic.ini` whose script head the database must match | `apps/api/alembic.ini` |
| `AIP_LOG_LEVEL` | JSON logs on stdout (structlog; stdlib and uvicorn routed through it; PII scrubbed) | `INFO` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OpenTelemetry OTLP/HTTP export of FastAPI, SQLAlchemy and Redis spans | unset: tracing off |

`GET /api/v1/health/live` never touches a dependency. `ready` returns 503 naming the failing check, and
each check is bounded by 2 s. Every response carries `X-Request-ID` (the caller's when safe, else a
UUIDv7), and every request logs one `request` line with `request_id` (and `tenant_id` when authenticated).

## Image, local stack and version endpoint (STACK-05)

`apps/api/Dockerfile` builds one image for the API and the worker (multi-stage with uv, UID 10001).
`infra/docker-compose.yml` runs the whole stack; every variable is listed in `/.env.example`.

```bash
GIT_SHA=$(git rev-parse HEAD) docker compose -f infra/docker-compose.yml up --build --wait
curl localhost:8000/api/v1/platform/version   # build and commit
```

`GET /api/v1/platform/version` (public) reports `BUILD_ID` and `GIT_SHA` (baked into the image).
`GET /api/v1/platform/version/dependencies` (signed in) reports library versions from
`importlib.metadata`, the Python version and Postgres `SHOW server_version` (read once per process;
`"unavailable"` when the database is down; still 200). Review 11 M5 took the versions off the public body.

### Client IP behind proxies (review 11 M1)

uvicorn runs with `--proxy-headers` and trusts `X-Forwarded-For` only from the peers in
`FORWARDED_ALLOW_IPS` (comma-separated IPs or CIDRs). The image default is loopback only, so a
direct client can never pick its own address. Every deployment sets it to its proxy hops: the
compose stacks use the private Docker ranges, and AWS sets the VPC CIDR (the ALB's subnets). The
login rate limit and the session and audit IPs all read `request.client.host`, which is then the
rightmost address that did not come from a trusted hop.
