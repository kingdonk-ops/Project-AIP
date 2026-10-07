-- DATABASE-08 / DATABASE-02 / ADR 0002: one-time cluster bootstrap, run by a superuser while
-- connected to the application database (Testcontainers fixture, compose init, RDS bootstrap
-- runbook). Idempotent: safe to run again.
--
-- Roles are cluster objects, so they are created here and not by Alembic revisions (ADR 0011):
--   aip_owner     migrator; owns the database, schemas and every table. Used only by aip-db.
--   aip_app       the API. LOGIN, not an owner of anything, no BYPASSRLS: RLS always applies.
--   aip_jobs      the worker (Procrastinate tables and outbox publish columns, granted later).
--   aip_readonly  reporting. SELECT only, still subject to RLS, read-only transactions.
-- None of them is SUPERUSER, CREATEDB, CREATEROLE, REPLICATION or BYPASSRLS. The revision
-- 202610072200_platform_roles refuses to run if any of them is missing or privileged.
--
-- Passwords: none lives in this file or anywhere in the repository. Each is read from a
-- custom setting and applied only when it is non-empty:
--   aip.owner_password, aip.app_password, aip.jobs_password, aip.readonly_password
-- Dev/test pass them in the environment of the psql process, e.g.
--   PGOPTIONS='-c aip.owner_password=... -c aip.app_password=...' \
--     psql -v ON_ERROR_STOP=1 -f db/bootstrap/00_cluster.sql <superuser url>
-- Production (the secrets flow, e.g. the RDS bootstrap runbook) reads them from the secrets
-- manager and passes either a pre-hashed SCRAM verifier ('SCRAM-SHA-256$4096:...', which
-- Postgres stores as given, so the clear text never reaches the server; preferred) or, if it must
-- send clear text, runs this session with logging off (PGOPTIONS adds -c log_statement=none
-- -c log_min_messages=fatal -c log_min_error_statement=panic), because an error inside the
-- ALTER ROLE ... PASSWORD below would otherwise echo the statement in the server log.

DO $bootstrap$
DECLARE
  spec record;
  pw text;
BEGIN
  FOR spec IN
    SELECT * FROM (VALUES
      ('aip_owner', 'aip.owner_password'),
      ('aip_app', 'aip.app_password'),
      ('aip_jobs', 'aip.jobs_password'),
      ('aip_readonly', 'aip.readonly_password')
    ) AS r (name, setting)
  LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = spec.name) THEN
      EXECUTE format(
        'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
        spec.name);
    ELSIF EXISTS (
      SELECT 1 FROM pg_roles
      WHERE rolname = spec.name
        AND (NOT rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication
             OR rolbypassrls)
    ) THEN
      EXECUTE format(
        'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
        spec.name);
    END IF;

    pw := coalesce(current_setting(spec.setting, true), '');
    IF pw <> '' THEN
      EXECUTE format('ALTER ROLE %I PASSWORD %L', spec.name, pw);
    END IF;
  END LOOP;

  -- Reporting sessions start read-only (RLS and grants still decide what they can see).
  IF NOT EXISTS (
    SELECT 1 FROM pg_db_role_setting s JOIN pg_roles r ON r.oid = s.setrole
    WHERE r.rolname = 'aip_readonly' AND s.setdatabase = 0
      AND 'default_transaction_read_only=on' = ANY (s.setconfig)
  ) THEN
    ALTER ROLE aip_readonly SET default_transaction_read_only = on;
  END IF;

  EXECUTE format('ALTER DATABASE %I OWNER TO aip_owner', current_database());

  -- Only the AIP roles may connect to this database (the owner and superusers always can).
  EXECUTE format('REVOKE CONNECT, TEMPORARY ON DATABASE %I FROM PUBLIC', current_database());
  EXECUTE format(
    'GRANT CONNECT ON DATABASE %I TO aip_app, aip_jobs, aip_readonly', current_database());
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
