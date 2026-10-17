# Runbook: bootstrap an empty Amazon RDS for PostgreSQL instance (OPS-16)

This is the "RDS bootstrap runbook" that `db/bootstrap/00_cluster.sql` refers to. It turns a new,
empty RDS PostgreSQL 16 instance into one `aip-db migrate` can migrate. Run it once per instance
(staging, production). It is idempotent, so running it again is safe.

**You need:** the RDS instance from OPS-07 (its parameter group already sets `rds.force_ssl = 1`
and `password_encryption = scram-sha-256`). You also need the master user's password and the five
role passwords in AWS Secrets Manager, and a host inside the VPC with `psql` 16 and the API image
(a bastion, or an ECS one-off task).

## What is different on RDS

RDS has no `SUPERUSER`. The master user is a member of `rds_superuser` and has `CREATEROLE` and
`CREATEDB`. `apps/api/tests/platform/db/test_rds_bootstrap.py` runs `00_cluster.sql` as exactly
such a role on a fresh cluster, and found this:

| Statement | As a CREATEROLE + CREATEDB database owner | What this runbook does |
|---|---|---|
| `CREATE ROLE aip_* ... NOBYPASSRLS` and the role flags | works | nothing extra |
| `ALTER ROLE ... PASSWORD` | works for roles it created | nothing extra |
| `ALTER DATABASE ... OWNER TO aip_owner` | **fails** (`must be able to SET ROLE "aip_owner"`), and the whole bootstrap block rolls back | run with `createrole_self_grant = 'set, inherit'`, so the master is granted the roles it creates |
| `REVOKE CONNECT, TEMPORARY ... FROM PUBLIC`, `GRANT CONNECT` | works | nothing extra |
| `CREATE SCHEMA aip_meta AUTHORIZATION aip_owner`, `REVOKE CREATE ON SCHEMA public` | works (with the self grant) | nothing extra |
| `CREATE EXTENSION vector` | **fails** off RDS (`must be superuser`) | on RDS, `rds_superuser` may create it because pgvector is on the RDS extension allow-list. Verify in step 4 |

After the bootstrap, `aip-db migrate` as `aip_owner` passes, including the platform-roles
revision's privilege check (the test runs it too).

## Steps

1. **Read the secrets** (never echo them or write them to disk):

   ```bash
   export PGHOST=<rds-endpoint> PGPORT=5432 PGSSLMODE=verify-full PGSSLROOTCERT=/etc/ssl/certs/rds-global-bundle.pem
   export PGUSER=<master-user> PGPASSWORD="$(aws secretsmanager get-secret-value --secret-id aip/<env>/rds-master --query SecretString --output text)"
   ```

   The API image ships the RDS CA bundle at `/etc/ssl/certs/rds-global-bundle.pem` (STACK-07).

2. **Create the databases**, owned by the master for now (the bootstrap hands `aip` to
   `aip_owner`). Keycloak's database and role follow the Keycloak runbook:

   ```bash
   psql -d postgres -v ON_ERROR_STOP=1 -c 'CREATE DATABASE aip' -c 'CREATE DATABASE keycloak'
   ```

3. **Run the bootstrap** connected to `aip`. Pass each role password as a pre-hashed SCRAM
   verifier (`SCRAM-SHA-256$4096:...`, generated from the secret on the bastion), so the clear text
   never reaches the server. If you must send clear text, add the logging-off options shown below.
   `createrole_self_grant` is required (see the table):

   ```bash
   PGOPTIONS="-c createrole_self_grant=set,inherit \
     -c aip.owner_password=$OWNER_SCRAM -c aip.app_password=$APP_SCRAM \
     -c aip.jobs_password=$JOBS_SCRAM -c aip.readonly_password=$READONLY_SCRAM \
     -c aip.audit_writer_password=$AUDIT_WRITER_SCRAM" \
     psql -d aip -v ON_ERROR_STOP=1 -f db/bootstrap/00_cluster.sql
   # clear-text fallback only: also add -c log_statement=none -c log_min_messages=fatal -c log_min_error_statement=panic
   ```

   It must end without an error. If `CREATE EXTENSION vector` fails, RDS has not allowed
   pgvector for this engine version: upgrade the engine minor version or add `vector` to the
   parameter group's `rds.allowed_extensions` (if set), then run step 3 again.

4. **Check the result:**

   ```sql
   -- every AIP role exists and none is privileged
   SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
   FROM pg_roles WHERE rolname LIKE 'aip\_%' ORDER BY 1;
   -- aip_owner owns the database; PUBLIC cannot connect
   SELECT pg_get_userbyid(datdba), has_database_privilege('public', 'aip', 'CONNECT')
   FROM pg_database WHERE datname = 'aip';
   -- pgvector is installed
   SELECT extversion FROM pg_extension WHERE extname = 'vector';
   ```

   Expected: five `aip_*` rows, all `f`; `aip_owner | f`; one `extversion` row.

5. **Migrate** as `aip_owner` with the migrator image (it refuses to run in production without
   `DB_SSLMODE=verify-full`):

   ```bash
   docker run --rm -e AIP_ENV=production -e DB_SSLMODE=verify-full \
     -e DATABASE_MIGRATOR_URL="postgresql://aip_owner:<from secrets>@<rds-endpoint>:5432/aip" \
     aip-migrator:<tag>
   ```

   In AWS this is the migrator ECS task that OPS-07's pipeline runs before each deploy. It must
   print the revisions it applied and exit 0. A second run applies nothing.

6. **Point the services at it:** `DATABASE_URL` uses `aip_app`, `DATABASE_JOBS_URL` uses `aip_jobs`,
   and the audit writer uses `aip_audit_writer`, all with `DB_SSLMODE=verify-full` (STACK-07). The
   master user is not used by any service. Rotate its password into Secrets Manager and keep it for
   break-glass only.

## Still to confirm on a real RDS instance

The local test proves everything above except what only RDS can show. Record the results here on
the first staging bootstrap:

- [ ] `CREATE EXTENSION vector` succeeds as the master user (pgvector allow-listed).
- [ ] `createrole_self_grant` is settable by the master user through `PGOPTIONS` (PostgreSQL 16
      makes it user-settable; RDS has not been seen to restrict it).
- [ ] `REVOKE CONNECT ... FROM PUBLIC` does not lock out `rdsadmin` (RDS's own maintenance role
      connects as a superuser, so it should not be affected).
