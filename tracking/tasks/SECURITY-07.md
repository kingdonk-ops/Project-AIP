# SECURITY-07 — Tenant IP allow-list and session policy
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07); identity per ADR 0005 rev 2 -->

| Field | Value |
|---|---|
| Module | [`security`](../../docs/blueprint/modules/security/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | IDENTITY-03 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/security/README.md`](../../docs/blueprint/modules/security/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module, especially [0005](../../docs/adr/0005-identity-architecture.md) rev 2: Keycloak enforces staff MFA through its realm authentication flow, and IDENTITY-03 owns session timeouts in `tenant_auth_policy`
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Enforce per-tenant IP allow-lists and add security headers in the FastAPI backend. Apply the tenant's session timeouts through IDENTITY-03, which owns them (`tenant_auth_policy.session_policy`). Staff MFA is enforced by the Keycloak realm flow and checked by IDENTITY-01/04, so this task adds no MFA setting.

- **depends on**:
  - SECURITY-02
- **files**:
  - apps/api/aip/modules/security/headers.py
  - apps/api/aip/modules/security/ip_allowlist.py
  - apps/api/aip/modules/security/tests/test_ip_allowlist.py
- **steps**:
  - 1. Store `ip_allowlist` (a CIDR list) in tenant_settings. Do not add `session_timeout_minutes` or `mfa_required`. Session timeouts are read from and written to IDENTITY-03's `tenant_auth_policy` through identity's `api.py`. MFA is not a tenant toggle: Keycloak always requires it for local accounts, and brokered accounts rely on the customer IdP plus step-up.
  - 2. Add middleware: if an allow-list is set and the client IP is outside it, return 403.
  - 3. Read the IP only from trusted proxy headers (configured hop count).
  - 4. Do not re-implement idle timeout. IDENTITY-03's session dependency already enforces it from `tenant_auth_policy`. This task only checks that it applies (integration test below). Also apply the allow-list on `GET /api/v1/auth/oidc/callback`, which returns 403 `IP_NOT_ALLOWED` before issuing a session. Keycloak's own pages are not tenant-filtered.
  - 5. Add security headers and CSP in the same middleware.
  - 6. Log denials to audit_log.
- **acceptance**:
  - An IP outside the list gets 403.
  - An expired idle session gets 401.
  - Security headers are present on all responses.
- **tests**:
  - **e2e**:
    - Tenant admin sets the allow-list in settings; a login from another IP is refused.
  - **integration**:
    - Tenant with the allow-list set, request from an outside IP returns 403 and an audit row is written.
    - With `tenant_auth_policy.session_policy.staff.idleMin=30`, a session idle for 31 minutes returns 401 `SESSION_EXPIRED` (enforced by IDENTITY-03; this test guards the integration).
    - With the allow-list set, completing the Keycloak sign-in from an outside IP ends at the callback with 403 `IP_NOT_ALLOWED`, and no `user_session` row is created.
  - **unit**:
    - 10.0.0.5 in ['10.0.0.0/24'] is allowed; 10.0.1.5 is denied.
    - A spoofed X-Forwarded-For beyond the trusted hop count is ignored.

## Carried forward from IDENTITY-01 (non-blocking)

- The login rate limit keys on the client address. Behind Coolify/nginx or an ALB that is the proxy's address, so only trust `X-Forwarded-For` from configured proxy hops (uvicorn `--forwarded-allow-ips` or an explicit trusted-proxy list) and test that a spoofed header from an untrusted peer is ignored.
