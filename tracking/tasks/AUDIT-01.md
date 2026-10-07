# AUDIT-01 — Append-only hash-chained audit_log, writer role, REVOKE

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`audit`](../../docs/blueprint/modules/audit/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-05, DATABASE-05 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/audit/README.md`](../../docs/blueprint/modules/audit/README.md)
3. ADRs: 0002 (roles, `withTenant`, append-only template, Kysely only in `platform/db`), 0004 (layout)
4. Only if the step needs it: the `audit_log` and `audit_chain_heads` tables in [`data-model.md`](../../docs/blueprint/modules/audit/data-model.md); the "Tamper-evidence" recommendation in [`docs/reviews/01-security.md`](../../docs/reviews/01-security.md)

## Spec

Create the tamper-evident store: a per-tenant, per-stream hash-chained `audit_log` that only a dedicated writer role can insert into and that no runtime role can update or delete, plus a pure hash function that the verifier (AUDIT-03) reuses unchanged.

- **files**:
  - db/migrations/<timestamp>_audit_log_chain.sql
  - apps/api/src/modules/audit/ (scaffold: module.ts, api.ts, manifest.json, permissions.ts)
  - apps/api/src/modules/audit/chain-hash.ts
  - apps/api/src/modules/audit/chain-writer.ts
  - apps/api/src/modules/audit/schemas.ts
  - apps/api/src/modules/audit/tests/
- **steps**:
  - 1. Read DATABASE-05's merged migration first. If it already created a placeholder `audit_log` or the generic append-only grant helper, alter or reuse them; do not duplicate.
  - 2. Write one migration from the `db/templates/` append-only template. `audit_log` has id (uuidv7), tenant_id, stream (`audit`; `security` is reserved for AUDIT-02), seq bigint, project_id, asset_id, asset_path ltree, actor_id, on_behalf_of_id, auth_strength, source_module, record_table, record_id, event_type, summary_key, payload jsonb (before/after), reason_for_change, flags text[], source_ip inet, device, source_event_id uuid, supersedes_id uuid, prev_hash bytea, hash bytea, occurred_at and created_at. There is no updated_at and no deleted_at. A correction is a new row with `supersedes_id`, never an edit. Add unique (tenant_id, stream, seq), unique (tenant_id, source_event_id) WHERE source_event_id IS NOT NULL, (tenant_id, project_id, occurred_at desc), (record_table, record_id, occurred_at), (tenant_id, actor_id, occurred_at), GiST (asset_path), and GIN (flags) WHERE flags <> '{}'.
  - 3. `audit_chain_heads` has (tenant_id, stream) as its PK, last_seq, last_hash and updated_at.
  - 4. Roles: create `aip_audit_writer` (LOGIN, NOSUPERUSER, NOBYPASSRLS, not an owner; the password is set by infra or tests, never in SQL). Grant it INSERT and SELECT on audit_log, and SELECT, INSERT and UPDATE on audit_chain_heads. Grant `aip_app` and `aip_readonly` SELECT only on audit_log. REVOKE UPDATE, DELETE and TRUNCATE on audit_log from PUBLIC and every runtime role, and add a `BEFORE UPDATE OR DELETE` trigger that raises, so the owner cannot edit rows by accident either. Use FORCE RLS on both tables with the ADR 0002 NULLIF policy (USING and WITH CHECK).
  - 5. In chain-hash.ts, write a pure function with only `node:crypto` and a JCS (RFC 8785) canonicaliser as dependencies, and no imports from platform or other modules. `computeHash(prevHash, entry)` is `sha256(prevHash ‖ JCS(entry))` over a fixed field list: tenant_id, stream, seq, occurred_at (ISO-8601 UTC, microseconds), actor_id, on_behalf_of_id, auth_strength, source_module, record_table, record_id, event_type, summary_key, payload, reason_for_change, flags (sorted), project_id, asset_id, source_event_id and supersedes_id. The genesis prev_hash is 32 zero bytes. Export `HASH_SPEC_VERSION = 1` and document the field list in a comment as the contract.
  - 6. In chain-writer.ts, `appendAuditEntries(db, tenantId, stream, entries[])` runs in one transaction with `app.tenant_id` set. It does `SELECT … FROM audit_chain_heads WHERE tenant_id=$1 AND stream=$2 FOR UPDATE` (inserting the head on first use), assigns consecutive seq values, computes the hashes, inserts the rows and updates the head. It takes a Kysely handle that connects as `aip_audit_writer` through a separate pool exported by `platform/db` (add the pool factory there only if it is missing, and flag that in the PR). Inserting an existing `source_event_id` is a no-op that returns the existing seq, so redelivery is safe.
  - 7. Expose `AuditApi.append` (writer side, used by AUDIT-02) and the entry Zod schema from api.ts. Declare permissions `audit.log.read` and `audit.activity.view` in the manifest; they are separate from tenant admin and enforced in AUDIT-04.
- **acceptance**:
  - aip_app and aip_audit_writer get `permission denied` for UPDATE, DELETE and TRUNCATE on audit_log. aip_app also cannot INSERT.
  - Concurrent appends for one tenant produce a gap-free seq and a valid chain. Different tenants' chains are independent.
  - Recomputing every hash from the rows with chain-hash.ts reproduces the stored hashes exactly.
  - No runtime role has BYPASSRLS or owns audit tables, and TESTING-02's schema guard passes. The append-only exemption for soft delete is recorded.
- **tests**:
  - **unit**:
    - `computeHash(ZERO32, fixtureEntry)` equals the committed golden hex value in `tests/fixtures/chain-v1.json`. Changing the order of payload keys gives the same hash (JCS), and changing one payload value gives a different hash.
    - `flags:['override','force_unlock']` and `['force_unlock','override']` hash identically.
    - `occurred_at` `2026-10-07T01:02:03.000004Z` serialises with 6 fractional digits.
  - **integration** (Testcontainers Postgres, with the real roles):
    - As aip_app: `UPDATE audit_log SET payload='{}'`. Expected: permission denied. `DELETE FROM audit_log`. Expected: permission denied. `INSERT INTO audit_log …`. Expected: permission denied.
    - As the owner role: `UPDATE audit_log SET event_type='x'`. Expected: the trigger raises `audit_log is append-only`.
    - Run 20 parallel `appendAuditEntries` calls of 5 entries each for tenant A. Expected: seq 1..100 with no gaps or duplicates, and every row's prev_hash equals the previous row's hash.
    - Append for tenants A and B, then as aip_app with `app.tenant_id=A` run `SELECT count(*)`. Expected: only A's rows. With no tenant set. Expected: 0.
    - Append the same `source_event_id` twice. Expected: 1 row, and the second call returns the first seq.
    - `SELECT rolbypassrls FROM pg_roles WHERE rolname IN ('aip_app','aip_audit_writer')`. Expected: both false.
  - **e2e**:
    - With the compose stack running, a script appends 3 entries for kaefer-demo through AuditApi, then recomputes the chain from a plain `SELECT … ORDER BY seq` using chain-hash.ts. Expected: all 3 hashes match and the head equals hash #3.
