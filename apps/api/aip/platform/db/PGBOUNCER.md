# PgBouncer compatibility (DATABASE-02, ADR 0002)

The API can reach Postgres directly (a bounded asyncpg pool, `DB_POOL_MODE=direct`, the default)
or through PgBouncer (`DB_POOL_MODE=pgbouncer`). Tenant isolation is safe in both. These rules
keep it that way.

## Rules

1. **Transaction pooling only.** Run PgBouncer with `pool_mode = transaction`. Session pooling
   works too, but gives no multiplexing. Statement pooling breaks multi-statement transactions,
   so it is not supported.
2. **The tenant is transaction-scoped.** `with_tenant` runs
   `select set_config('app.tenant_id', :t, true)` inside the transaction it opens. The `true`
   means the setting ends with the commit or rollback, which is also the moment PgBouncer hands
   the server connection to another client. A tenant therefore never outlives its transaction on
   a server connection. Session-level `SET` (or `set_config(..., false)`) would leak to the next
   client. It is banned by `aip-db lint` for migrations and by
   `tests/platform/db/test_session.py` for `aip/`.
3. **Statement cache off.** In `pgbouncer` mode `engine.py` passes `statement_cache_size=0` and
   `prepared_statement_cache_size=0` to asyncpg. It also names each prepared statement uniquely
   (`prepared_statement_name_func`), so a name prepared on one server connection is never looked
   up on another. Without this, asyncpg fails with `prepared statement "__asyncpg_stmt_N__" does
   not exist`. `test_session_pgbouncer.py` shows this failure in direct mode. With
   `max_prepared_statements = 0`, PgBouncer does not track prepared statements itself, and the
   test passes. PgBouncer 1.21 and later can track them (`max_prepared_statements > 0`). That is
   allowed but not relied on.
4. **Fail closed.** If a transaction reaches Postgres without the setting, `app.tenant_id` is
   unset or `''`. The RLS policies compare `tenant_id` to `NULLIF(..., '')::uuid`, which is NULL,
   so reads see 0 rows and writes fail `WITH CHECK` (SQLSTATE 42501).
5. **Migrations bypass PgBouncer.** `aip-db migrate` uses `DATABASE_MIGRATOR_URL`, a direct
   connection as `aip_owner`, because it holds a session-level advisory lock.
6. **No RDS Proxy on the RLS path** until session pinning has been measured (ADR 0002). RDS Proxy
   pins a session when it sees `set_config`, which can remove the pooling benefit.

## Test

`apps/api/tests/platform/db/test_session_pgbouncer.py` puts PgBouncer in transaction mode in
front of Postgres, with 4 server connections and no prepared-statement tracking. It runs 20
parallel `with_tenant` transactions that alternate between tenants A and B, three times over. It
expects zero cross-tenant rows, no prepared-statement errors, at most 4 server backends, and no
tenant on a pooled connection afterwards. PgBouncer comes from a local `pgbouncer` binary
(`AIP_TEST_PGBOUNCER` or `PATH`) or the `edoburu/pgbouncer` image through Testcontainers.
