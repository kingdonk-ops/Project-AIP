# ADR 0028: Platform rows use the nil-UUID platform tenant, readable by all, written only by aip_owner

- **Status:** proposed
- **Date:** 2026-10-14
- **Affects:** terms (TERMS-01, later TERMS-*); any module with platform reference rows (for example `unit_definition`, built-in packs); `aip.platform.db.session`

## Context

Some tables hold both tenant rows and platform rows: the terms dictionary keeps the en-AU defaults
(`term_key`) beside tenant overrides, and built-in market packs beside tenant packs. The data model
says "platform tenant for global rows; RLS permits read of platform rows". Every table still needs
`tenant_id` and FORCE RLS (hard rule), and the schema guard (TESTING-02) requires a permissive
FOR ALL policy keyed on `app.tenant_id`. `with_tenant` refuses the nil UUID, so application code
cannot bind it by accident.

## Decision

- The platform tenant is the nil UUID, `PLATFORM_TENANT_ID` in `aip.platform.db.session`. It is not a
  row in `tenants` and platform rows have no FK to `tenants`.
- A table that holds platform rows replaces the template's `tenant_isolation` policy with:
  - `tenant_write` FOR ALL, USING and WITH CHECK
    `tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid AND (tenant_id <> <nil> OR current_user = 'aip_owner')`;
  - `platform_read` FOR SELECT USING `tenant_id = <nil>`.

  A tenant reads its own rows and platform rows and writes only its own rows. `aip_app` can never
  write a platform row, even with `app.tenant_id` set to the nil UUID by hand.
- Platform rows are written only at deploy time, as `aip_owner`, through
  `with_platform_tenant(engine)`. It refuses any other login, then binds the nil UUID for the
  transaction. The engine is `create_migrator_engine(DATABASE_MIGRATOR_URL)`.
- Loaders of platform rows run as one-shot jobs right after the migrator (the compose
  `terms-load` service). They are idempotent upserts, not seeds, so they also run in production.

## Consequences

- With no tenant bound, these tables show their platform rows (never tenant rows). Tests that assert
  "0 rows with no tenant" must target tenant-only tables.
- Unique indexes that span tenants (for example `term_key (key)`) make a key's existence visible
  across tenants. That is acceptable for platform-defined keys.
- A future platform table copies the two policies from `202610141000_terms_tables`.
