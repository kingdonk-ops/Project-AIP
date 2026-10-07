-- DATABASE-08 / ADR 0002: one-time cluster bootstrap, run by a superuser while connected to the
-- application database (Testcontainers fixture, compose init, RDS bootstrap runbook).
-- Idempotent: safe to run again.
--
-- It creates the migrator role `aip_owner` and nothing else: DATABASE-02 owns aip_app, aip_jobs and
-- aip_readonly. No password lives in this file. Pass one for dev/test with
--   PGOPTIONS='-c aip.owner_password=...' psql -v ON_ERROR_STOP=1 -f db/bootstrap/00_cluster.sql <url>
-- or set it afterwards with ALTER ROLE (production: from the secrets manager).

DO $bootstrap$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aip_owner') THEN
    CREATE ROLE aip_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  ELSE
    ALTER ROLE aip_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;

  IF coalesce(current_setting('aip.owner_password', true), '') <> '' THEN
    EXECUTE format('ALTER ROLE aip_owner PASSWORD %L', current_setting('aip.owner_password'));
  END IF;

  EXECUTE format('ALTER DATABASE %I OWNER TO aip_owner', current_database());
END
$bootstrap$;

-- Alembic keeps its version table here (version_table_schema = aip_meta).
CREATE SCHEMA IF NOT EXISTS aip_meta AUTHORIZATION aip_owner;
ALTER SCHEMA aip_meta OWNER TO aip_owner;

-- Nobody but the owner creates objects in public.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- pgvector is not a trusted extension, so a superuser creates it here. The baseline revision
-- creates the trusted ones and fails with `missing extension vector` if this line did not run.
CREATE EXTENSION IF NOT EXISTS vector;
