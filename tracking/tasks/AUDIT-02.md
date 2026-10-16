# AUDIT-02 — Audit writer from outbox + security stream (auth events)

<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-16); identity's auth emits and the Keycloak e2e moved to AUDIT-06 as step 5 allows -->

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
3. ADRs: 0003 (outbox, dispatcher), 0002 (roles), 0005 (auth events come from the app, not Keycloak), 0021 (two streams, 3-year security retention)
4. Only if the step needs it: the `security_audit_events` table in [`data-model.md`](../../docs/blueprint/modules/audit/data-model.md)

## Spec

Write every domain event into the hash chain automatically, so modules only emit to the outbox.
Route authentication, permission-change and export events into a separate, equally hash-chained
security stream.

- **files**:
  - apps/api/migrations/versions/202610161300_security_audit_events.py
  - apps/api/aip/platform/events/subscribers.py (catch-all subscriptions)
  - apps/api/aip/modules/audit/events.py (the subscriber), writer.py, mapping.py, redact.py, security_chain.py
  - apps/api/aip/modules/audit/repository.py, schemas.py, tables.py, api.py, manifest.toml
  - apps/api/tests/fixtures/audit.py (`expect_audited`)
  - apps/api/aip/modules/audit/tests/
  - infra/docker-compose.yml, infra/coolify/*, infra/docker/postgres/init/10-aip-bootstrap.sh, .env.example (`aip_audit_writer` login)
- **steps**:
  - 1. Migration `security_audit_events`, append-only like `audit_log`: id, tenant_id, seq, actor_id, event_type, target_ref, auth_strength, source_ip inet, device, detail jsonb, source_event_id, prev_hash, hash, occurred_at, created_at. Unique (tenant_id, seq) and (tenant_id, source_event_id); indexes (tenant_id, event_type, occurred_at) and (tenant_id, actor_id, occurred_at). Same grants, REVOKE, raise-trigger and FORCE RLS as AUDIT-01. Chain heads and checkpoints reuse `audit_chain_heads` / `audit_chain_checkpoints` with stream `security`. No mutable column (SIEM forwarding is out of scope).
  - 2. The outbox subscriber registry accepts a catch-all subscription (`"*"`, declared in the manifest as `[[subscribes]] name = "*"`), delivered after the event's own subscribers. The audit module registers one; it maps the event and appends through `aip_audit_writer` (its own transaction, not the subscribers' `aip_app` one) for the event's tenant. `source_event_id` (the event id) makes redelivery a no-op; a failed write raises, so the event stays unpublished and is retried.
  - 3. `mapping.py` builds entries from a domain event: actor, project and asset from the envelope; `source_module` from the name prefix; record table and id from the aggregate; `summary_key = audit.summary.<event_name>`; payload `{before, after}` when present, else the payload; flags from `payload.flags`; reason from `payload.reason`. `auth.*`, `session.*`, `access.*`, `permission.*`, `export.*` and `audit.security_event` go to the security stream; `user.deactivated` goes to both.
  - 4. `redact.py` replaces values of keys matching `/password|secret|token|otp|recovery|private_key/i` at any depth with `"[redacted]"`, before hashing.
  - 5. Identity's auth and session emits: **moved to AUDIT-06** (identity emitted no events; its login paths are security code IDENTITY-04 also changes).
  - 6. `AuditApi.record_security_event(conn, input)` emits `audit.security_event` v1 through the outbox for security events with no domain event (for example a sensitive read), so ordering and idempotency are the same.
  - 7. From this task on, "audit events emitted" means the event is in `audit_log` or `security_audit_events`. `tests.fixtures.audit.expect_audited(...)` lets later modules assert it (modules may import only each other's `api`).
- **acceptance**:
  - Any event emitted to `domain_events` appears exactly once in the right stream within one dispatcher cycle, with a valid chain.
  - A failed audit write leaves the event unpublished; the dispatcher retries it and never drops it silently.
  - No secret value appears in either table.
  - Security events are only in the security stream, never in `audit_log` (project timelines).
- **tests**:
  - **unit**: the `project.updated`, `auth.login.failed` and `user.deactivated` mappings; the redaction example.
  - **integration** (real Postgres, real dispatcher): 50 `project.updated` events give seq 1..50 with a valid chain; redelivery keeps 50 rows; a writer failure on the first attempt leaves attempts=1 and no row, and the next cycle writes it once; `auth.login.succeeded` gives 1 security row and 0 audit rows; `payload.after.password='hunter2'` is stored redacted; tenants A and B in one batch give two chains from seq 1.
  - **e2e**: moved to AUDIT-06 (it needs identity's emits).
