#!/bin/sh
# First start of the compose Postgres volume only (docker-entrypoint-initdb.d), as the superuser:
# 1. db/bootstrap/00_cluster.sql (DATABASE-08, ADR 0012): roles aip_owner and aip_app (and the
#    other runtime roles, without a dev password), schema aip_meta, extension vector;
# 2. Keycloak's own role and database (ADR 0005).
# Passwords come from the environment (obviously fake dev defaults in infra/docker-compose.yml).
set -eu

PGOPTIONS="-c aip.owner_password=${AIP_OWNER_PASSWORD} -c aip.app_password=${AIP_APP_PASSWORD}" psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /aip/bootstrap/00_cluster.sql

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v kc_password="$KEYCLOAK_DB_PASSWORD" <<'SQL'
CREATE ROLE keycloak LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'kc_password';
CREATE DATABASE keycloak OWNER keycloak;
SQL
