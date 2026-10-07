# AUDIT-02 — Audit writer from outbox + security stream (auth events)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`audit`](../../docs/blueprint/modules/audit/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-07, AUDIT-01, IDENTITY-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/audit/README.md`](../../docs/blueprint/modules/audit/README.md)
3. ADRs: 0003 (outbox `domain_events`, dispatcher, idempotent `jobId = event_id`, worker re-enters `withTenant`), 0002 (roles), 0005 (auth events come from the app, not Keycloak)
4. Only if the step needs it: the `security_audit_events` table in [`data-model.md`](../../docs/blueprint/modules/audit/data-model.md)

## Spec

Write every domain event into the hash chain automatically, so modules only emit to the outbox. Route authentication, permission-change and export events into a separate, equally hash-chained security stream.

- **files**:
  - db/migrations/<timestamp>_security_audit_events.sql
  - apps/api/src/modules/audit/writer.subscriber.ts
  - apps/api/src/modules/audit/mapping.ts
  - apps/api/src/modules/audit/redact.ts
  - apps/api/src/modules/audit/security-stream.ts
  - apps/api/src/modules/audit/api.ts
  - apps/api/src/modules/audit/tests/
- **steps**:
  - 1. Write a migration for `security_audit_events`, append-only like audit_log: id, tenant_id, seq, actor_id, event_type, target_ref, auth_strength, source_ip inet, device, detail jsonb, source_event_id, prev_hash, hash, occurred_at and created_at. Add unique (tenant_id, seq), unique (tenant_id, source_event_id), (tenant_id, event_type, occurred_at) and (tenant_id, actor_id, occurred_at). Apply the same grants, REVOKE and raise-trigger as AUDIT-01, with FORCE RLS. Chain heads reuse `audit_chain_heads` with stream `security`. SIEM forwarding is out of scope, so there is no mutable column.
  - 2. In writer.subscriber.ts, register one catch-all subscriber with ARCH-07's subscriber registry for every event name. Per batch, it maps events to entries and calls `appendAuditEntries` once per (tenant, stream), using the `aip_audit_writer` pool inside `runWithContext` for the event's tenant. The `source_event_id` (event id) makes redelivery a no-op.
  - 3. In mapping.ts, build an audit entry from a domain event: actor_id, project_id, asset_id and asset_path from the envelope; source_module from the event name prefix; record_table and record_id from the aggregate; summary_key = `audit.summary.<event_name>`; payload = `{before, after}` when present, else the event payload; flags from `payload.flags`; reason_for_change from `payload.reason`. Events named `auth.*`, `session.*`, `access.*`, `permission.*`, `export.*` and `user.deactivated` go to the security stream, and `user.deactivated` goes to both streams.
  - 4. In redact.ts, before hashing, replace values of keys matching `/password|secret|token|otp|recovery|private_key/i` at any depth with `"[redacted]"`. The redaction runs before the hash, so the chain never contains secrets.
  - 5. Auth events: make sure IDENTITY-01/02 emit (or add them through their published API, not their tables) `auth.login.succeeded`, `auth.login.failed` (tenant resolved via login_directory; attempts whose tenant cannot be resolved are only logged, never written to a tenant chain), `auth.logout`, `auth.jit_provisioned` and `session.revoked`, with source IP, user agent and auth strength. If an emit is missing in the identity module, open a stub follow-up rather than editing identity code beyond a single `emit()` call.
  - 6. In security-stream.ts, add `AuditApi.recordSecurityEvent(input)` for synchronous security events that have no domain event (for example a sensitive read). It writes through the outbox, so ordering and idempotency are the same.
  - 7. Keep the staged DoD: from this task on, "audit events emitted" means the event appears in audit_log or security_audit_events. Add a test helper `expectAudited(eventName, {recordId})` to `tests/` so later modules can assert it.
- **acceptance**:
  - Any event emitted to `domain_events` by any module appears exactly once in the right stream within one dispatcher cycle, with a valid chain.
  - A failed audit write leaves the event unpublished; the dispatcher retries it and never drops it silently.
  - No secret value appears in either table.
  - Security events are readable only through the security stream; they are not mixed into project timelines.
- **tests**:
  - **unit**:
    - mapping on `{name:'project.updated', payload:{before:{name:'A'}, after:{name:'B'}}}` gives stream `audit`, source_module `projects`, summary_key `audit.summary.project.updated`, and payload `{before:{name:'A'}, after:{name:'B'}}`.
    - mapping on `auth.login.failed` gives stream `security`. `user.deactivated` gives both streams.
    - redact `{a:{password:'x', nested:[{api_token:'y'}]}, name:'ok'}` gives `{a:{password:'[redacted]', nested:[{api_token:'[redacted]'}]}, name:'ok'}`.
  - **integration** (Testcontainers Postgres and Redis, real dispatcher):
    - Emit 50 `project.updated` events for tenant A and run the dispatcher. Expected: 50 audit_log rows with seq 1..50 and a valid chain.
    - Mark the events unpublished again and redeliver. Expected: still 50 rows.
    - Make the writer pool fail on the first attempt. Expected: the event has attempts=1, no row is written, and the next cycle writes it once.
    - Emit `auth.login.succeeded` for user U. Expected: 1 row in security_audit_events and 0 in audit_log.
    - Emit an event with `payload.after.password='hunter2'`. Expected: the stored payload has `"[redacted]"`, and `SELECT … WHERE payload::text LIKE '%hunter2%'` returns 0.
    - Run events for tenants A and B in one batch. Expected: two independent chains, each starting at seq 1.
  - **e2e**:
    - Log in through Keycloak as the kaefer-demo admin, create a project and log out. Expected: security_audit_events has `auth.login.succeeded` and `auth.logout` for that user, and audit_log has `project.created` with the project id as record_id.
