#!/bin/bash
# SessionStart hook for Claude Code cloud sessions.
# Prepares a local Postgres 16 (ltree, pg_trgm, pgcrypto, pgvector) because the Docker
# daemon is not available here, so Testcontainers can't start. Tests read
# AIP_TEST_DATABASE_URL and fall back to it when Docker is unavailable (TESTING-01).
# Installs Python/TS dependencies once their lockfiles exist. Idempotent.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(pwd)}"

# --- Postgres 16 + extensions -------------------------------------------------
if ! dpkg -s postgresql-16-pgvector >/dev/null 2>&1; then
  if ! { apt-get update -q >/dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y -q postgresql-16-pgvector >/dev/null; }; then
    echo "warn: pgvector install failed; continuing without the vector extension" >&2
  fi
fi

command -v pg_lsclusters >/dev/null || { echo "error: PostgreSQL 16 is not installed in this image" >&2; exit 1; }
status=$(pg_lsclusters -h | awk '$1==16 && $2=="main" {print $4}')
if [[ "$status" != *online* ]]; then
  pg_ctlcluster 16 main start
fi

for _ in $(seq 1 30); do
  pg_isready -q -h localhost -p 5432 && break
  sleep 1
done
pg_isready -q -h localhost -p 5432 || { echo "error: Postgres did not become ready on localhost:5432" >&2; exit 1; }

# Test superuser + database. Superuser is needed so test fixtures can create the
# app roles (aip_owner, aip_app, aip_jobs, aip_readonly) and extensions per ADR 0002.
su postgres -c "cd /tmp && psql -q -v ON_ERROR_STOP=1" <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aip_test') THEN
    CREATE ROLE aip_test LOGIN SUPERUSER PASSWORD 'aip_test';
  END IF;
END
$$;
SQL
exists=$(su postgres -c "cd /tmp && psql -tAc \"SELECT 1 FROM pg_database WHERE datname='aip_test'\"")
if [[ "$exists" != "1" ]]; then
  su postgres -c "cd /tmp && createdb -O aip_test aip_test"
fi
su postgres -c "cd /tmp && PGOPTIONS=--client-min-messages=warning psql -q -d aip_test -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS ltree; CREATE EXTENSION IF NOT EXISTS pg_trgm; CREATE EXTENSION IF NOT EXISTS pgcrypto;'"
if dpkg -s postgresql-16-pgvector >/dev/null 2>&1; then
  su postgres -c "cd /tmp && PGOPTIONS=--client-min-messages=warning psql -q -d aip_test -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS vector;'"
fi

if [ -n "${CLAUDE_ENV_FILE:-}" ] && ! grep -qs AIP_TEST_DATABASE_URL "$CLAUDE_ENV_FILE"; then
  # Local dev-only credentials for a throwaway test database; not a secret.
  echo 'export AIP_TEST_DATABASE_URL="postgresql://aip_test:aip_test@localhost:5432/aip_test"' >> "$CLAUDE_ENV_FILE"
fi

# --- Python (uv) ----------------------------------------------------------------
if [ -f uv.lock ] && command -v uv >/dev/null; then
  uv sync --all-packages --frozen >&2
fi

# --- TypeScript (pnpm) ------------------------------------------------------------
if [ -f pnpm-lock.yaml ] && command -v pnpm >/dev/null; then
  pnpm install --frozen-lockfile >&2
fi
