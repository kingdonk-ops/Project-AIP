# ADR 0029: Platform-admin permissions live in the ops module, and the event catalogue reads across tenants through one SECURITY DEFINER function

- **Status:** accepted
- **Date:** 2026-10-15
- **Affects:** arch (ARCH-06, ARCH-07), audit (AUDIT-02), access (ACCESS-01), ops; `aip.platform.events`

## Context

ARCH-06 adds the versioned event registry and the `/admin/platform/events` catalogue API. Two
questions had no existing answer:

1. **Where do platform-admin permissions come from?** The permission catalogue (ACCESS-01) is built
   only from module manifests (`aip.modules.*`). The catalogue API is platform code
   (`aip.platform.events`, mounted by `aip.main` outside the module registry, like
   `/platform/modules`) and needs a permission, `platform.events.manage`, that no module declared.
   ADR 0017/0020 say platform operators have no standing access to tenant data and run on their own
   console; they do not say which module owns their permission codes.
2. **How does a tenant-scoped API read cross-tenant aggregates?** `domain_events` forces RLS and
   `aip_owner` is `NOBYPASSRLS` (ADR 0002, `db/bootstrap/00_cluster.sql`), so even a definer
   function owned by `aip_owner` sees nothing without an explicit policy. The catalogue's 24h
   published/failed figures must span every tenant, but must never expose a payload.

## Decision

- **Platform-admin permissions are declared by the `ops` module**, which already has
  `context = "platform"`. `ops/manifest.toml` now sets `permission_namespaces = ["ops", "platform"]`
  and declares `platform.events.manage` (privileged). Permission codes are a flat global namespace,
  so a code declared by `ops` gates routes that live under `aip.platform.*`. The event-catalogue
  router is mounted only when `platform.events.manage` is in the catalogue, so an app built from a
  module set without `ops` (test fixtures) does not mount routes whose permission is absent.
- **The event registry owns platform events.** `register_event(name, version, model, owner)` tracks
  the owning module; a module's manifest `events` and the models it registers must match exactly
  (`verify_manifest_events`). Platform-owned events (owner `"platform"`, e.g.
  `platform.event.deprecated`) are registered by the platform at boot and are exempt from the
  manifest cross-check, since they belong to no business module.
- **Released payload schemas are frozen in `packages/contracts/events`.** A registered model whose
  schema differs from its committed `<name>.v<version>.json` fails boot
  (`ReleasedSchemaChangedError`); `tools/codegen/export_event_schemas.py` writes the files and CI
  fails on any `git diff`. A payload change needs a new version.
- **Cross-tenant counts go through one SECURITY DEFINER function.** `platform_event_counts(since)`
  is owned by `aip_owner`, has a fixed `search_path`, is `STABLE`, and returns only
  `(event_name, event_version, published, failed)` — never a payload, tenant, actor or id. A
  permissive `FOR SELECT TO aip_owner` policy on `domain_events` lets this function (and only it)
  read every tenant's rows; `EXECUTE` is granted to `aip_app`. The deprecation flag lives in the
  global `platform_event_status` table (no `tenant_id`, no RLS; on the schema-guard allow-list).

## Consequences

- Platform-admin surfaces added later (dead-letter triage, replay, feature flags) declare their
  permissions in `ops` under the `platform` namespace, and their routes mount only where that
  permission exists. If platform permissions later outgrow `ops`, a dedicated `platform_admin`
  module can claim the `platform` namespace without touching callers.
- The catalogue exposes cross-tenant health without widening any runtime role's isolation:
  permissive policies are OR'd, so the owner-read policy adds a path only for `aip_owner`, which
  runs no runtime queries except this function. `aip_app`, `aip_jobs` and `aip_readonly` stay
  tenant-isolated.
- Deprecation is a flag, not a gate: a deprecated event still validates and emits (the catalogue
  shows `status: deprecated`). Blocking emission of deprecated events, if ever wanted, is a later
  decision.
- Modules now register events with `register_event(..., owner)` instead of the old
  `event_schemas.register(...)`; `emit` defaults to the process-wide registry.

## Amendment (2026-10-15, ENT-01 security review)

`platform.*` codes are **operator-only**: no tenant role, default or custom, may hold one. The ACCESS-02 role
service refuses them on create, update and clone (422 `OPERATOR_ONLY_PERMISSION`), and the default-role expansion
skips them. Without this a stepped-up tenant admin could put `platform.tenants.manage` in a custom role, assign it
to themselves and change any tenant's subscription. Until the operator realm (ADR 0017, OPS-12) issues operator
principals, nobody holds these codes in a running deployment, so the operator routes answer 403 to everyone
(fail closed); tests grant them through a test grant provider.
