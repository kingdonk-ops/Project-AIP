# API test fixtures

Every integration test runs against real Postgres 16 (ltree, pg_trgm, pgcrypto, pgvector). The
database is never mocked. All the plumbing lives in one module, `tests/fixtures/postgres.py`
(`tests/platform/db/conftest.py` only re-exports it for older imports).

## Which server

`select_postgres_source` picks, in order:

1. `AIP_TEST_DATABASE_URL`, a superuser URL (CI db job, local runs):
   `postgresql://aip_test:aip_test@localhost:5432/aip_test`.
2. Testcontainers `pgvector/pgvector:pg16`, when the variable is unset and Docker is reachable.
3. Neither: tests skip locally and fail when `CI` is set.

## Fixtures

| Fixture | Gives you |
|---|---|
| `pg_superuser_url` (session) | the server's superuser URL; cleans up roles the session created |
| `empty_db` | a new empty database (`aip_test_<hex>`), dropped afterwards |
| `bootstrapped_db` | `empty_db` after `db/bootstrap/00_cluster.sql` (roles, pgvector) |
| `migrated_db` | `bootstrapped_db` migrated to head by `aip-db migrate` as `aip_owner` |
| `tenant_db` | a `TenantDb`: an `aip_app` engine (pool 2, no overflow) on `migrated_db` |
| `owner_conn_for_seeding_only` | an `OwnerSeeder`: `ddl(sql)` and `insert(tenant, sql)` as `aip_owner` |

`aip_app` is `NOSUPERUSER NOBYPASSRLS` and owns nothing, so row-level security always applies.

```python
async def test_isolation(tenant_db: TenantDb, owner_conn_for_seeding_only: OwnerSeeder) -> None:
    seed = owner_conn_for_seeding_only
    seed.ddl(render_template("tenant_table", table="rls_probe", columns="note text"))
    seed.insert(
        TENANT_A_ID, f"INSERT INTO rls_probe (id, tenant_id) VALUES ('{uuid4()}', '{TENANT_A_ID}');"
    )
    async with tenant_db.with_tenant(TENANT_B_ID) as conn:  # kaefer-demo is A, tenant-b is B
        assert (await conn.execute(text("SELECT count(*) FROM rls_probe"))).scalar_one() == 0
```

`tenant_db.no_tenant()` gives an `aip_app` transaction with no tenant set (tenant tables show 0
rows, writes fail with SQLSTATE 42501). Tenant ids: `TENANT_A_ID` (`kaefer-demo`) and `TENANT_B_ID`
(`tenant-b`) from `tests/conftest.py`. A worked example is `tests/tenancy/test_rls_fixture.py`.

## The guard: no owner or superuser for tenant-data assertions

* Seeding returns nothing (`OwnerSeeder`), so it cannot back an assertion.
* `tenant_db` checks `assert_unprivileged_url` when it is built and `assert_unprivileged_role`
  (live: not SUPERUSER, not BYPASSRLS, owns no tables) on every connection it hands out; either
  raises `PrivilegedConnectionError`.
* `aip.platform.db.create_app_engine` also refuses such roles at connect time.
* Never read tenant data with `FreshDb.fetch`, `FreshDb.execute`, `owner_url` or `superuser_url`
  in an assertion; those bypass or own RLS and would pass for the wrong reason.

## Concurrency

Agents and CI jobs share one local cluster. Roles, `ALTER DATABASE` and grants on databases update
shared catalogs, and concurrent bootstraps used to fail with `tuple concurrently updated`.
`FreshDb.bootstrap` therefore runs through `cluster_ddl`: a session advisory lock taken in the
`postgres` database (advisory locks are per database, so a lock in the test database would not
serialise two test databases), plus `retry_concurrent_update` for the rare writer outside the
lock. `migrated_db` retries `aip-db migrate` the same way.
