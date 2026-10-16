# AUDIT-06 — Identity emits auth and session events into the security stream

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`identity`](../../docs/blueprint/modules/identity/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | AUDIT-02, IDENTITY-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`tracking/tasks/AUDIT-02.md`](AUDIT-02.md) (the security stream and its mapping)
3. ADRs: [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md), [0005](../../docs/adr/0005-identity-architecture.md) (auth events come from the app, not Keycloak)

## Spec

Split from AUDIT-02 step 5 (2026-10-16), as that step allows: identity emitted no domain events, and
its OIDC callback, logout, back-channel logout, JIT and revoke paths are security code that IDENTITY-04
also changes. AUDIT-02 routes any `auth.*` / `session.*` event to `security_audit_events`; this task
makes identity publish them.

- **files**:
  - apps/api/aip/modules/identity/events.py, manifest.toml (declare the events)
  - apps/api/aip/modules/identity/routes.py, jit.py, sessions.py (one `emit()` each)
- **steps**:
  - 1. Declare `auth.login.succeeded`, `auth.login.failed`, `auth.logout`, `auth.jit_provisioned` and `session.revoked` v1. Payload: `sourceIp`, `device` (user agent), `authStrength`, `targetRef` where it applies; no token or credential ever.
  - 2. Emit each in the transaction that records the outcome. `auth.login.failed` only when the tenant is resolved through `login_directory`; unresolved attempts are logged, never written to a tenant chain.
- **acceptance**:
  - A Keycloak sign-in, project create and sign-out leave `auth.login.succeeded` and `auth.logout` in `security_audit_events` and `project.created` in `audit_log`.
- **tests**:
  - **integration**: each path emits its event once; a failed login for an unknown tenant writes nothing.
  - **e2e**: log in through Keycloak as the kaefer-demo admin, create a project, log out; check both streams.
