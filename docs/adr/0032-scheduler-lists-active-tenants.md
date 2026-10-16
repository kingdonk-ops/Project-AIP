# ADR 0032: The scheduled-job trigger lists active tenants through one SECURITY DEFINER function

- **Status:** accepted
- **Date:** 2026-10-16
- **Affects:** ops (OPS-13), tenancy; database (DATABASE-02 roles)

## Context

OPS-13 adds one entry point for recurring work, `python -m aip.modules.ops.schedule enqueue <job>
--all-tenants`, triggered by a Coolify scheduled task now and by EventBridge Scheduler (ECS RunTask
with the API image) in AWS. `--all-tenants` must enqueue one job per active tenant.

No runtime role can list tenants: `tenants` has FORCE RLS keyed on `id = app.tenant_id`, and the only
cross-tenant policy is ENT-01's `real_customer_check` for `aip_owner`. ENT-01's snapshot CLI works
around this by taking tenants on the command line, which a fixed EventBridge rule cannot do.

The worker role `aip_jobs` also cannot create job rows (it reads and moves them; OPS-01), so the
scheduler enqueues as `aip_app`, through `with_tenant`, exactly as a request does.

## Decision

- Add the policy `scheduler_list_active ON tenants FOR SELECT TO aip_owner USING (status =
  'active')` and the SECURITY DEFINER function `ops_active_tenant_ids() RETURNS SETOF uuid`, owned by
  `aip_owner` with a fixed `search_path`, returning only the ids of active tenants. EXECUTE goes to
  `aip_app` only; PUBLIC, `aip_jobs` and `aip_readonly` get nothing.
- The scheduler calls it on a `before_tenant()` connection, then enqueues each tenant's job in that
  tenant's own `with_tenant` transaction, so every job row is still written under RLS.

## Consequences

- One trigger serves every tenant, and a new tenant is picked up on the next run.
- `aip_app` can learn which tenant ids are active (not names or any other column). Every
  authenticated request already knows its own tenant id, and ids are not secrets, so this is
  accepted. Nothing else about other tenants is exposed.
- `aip_owner` (the migrator) can now read active tenant rows; it already owns the table and runs only
  migrations.
