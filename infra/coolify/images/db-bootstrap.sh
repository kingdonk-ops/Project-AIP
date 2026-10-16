#!/bin/sh
# Demo `db-bootstrap` one-shot (OPS-11): run on every deploy, as the Postgres superuser, before the
# migrator and Keycloak. Idempotent, so it also repairs a volume that was initialised without it.
# 1. db/bootstrap/00_cluster.sql (DATABASE-08, ADR 0012): roles aip_owner, aip_app, aip_jobs,
#    aip_audit_writer and aip_readonly, schema aip_meta, extension vector; it (re)applies the
#    passwords given here.
# 2. Keycloak's own role and database (ADR 0005), created if missing; its password is (re)applied.
set -eu

PGOPTIONS="-c aip.owner_password=${AIP_OWNER_PASSWORD} -c aip.app_password=${AIP_APP_PASSWORD} -c aip.jobs_password=${AIP_JOBS_PASSWORD} -c aip.audit_writer_password=${AIP_AUDIT_WRITER_PASSWORD}" \
  psql -v ON_ERROR_STOP=1 -d aip -f /aip/bootstrap/00_cluster.sql

psql -v ON_ERROR_STOP=1 -d aip -v kc_password="$KEYCLOAK_DB_PASSWORD" <<'SQL'
SELECT 'CREATE ROLE keycloak LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'keycloak') \gexec
ALTER ROLE keycloak PASSWORD :'kc_password';
SELECT 'CREATE DATABASE keycloak OWNER keycloak'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'keycloak') \gexec
SQL

echo "db-bootstrap: roles, schema, extension and the keycloak database are in place"
