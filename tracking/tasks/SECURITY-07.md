# SECURITY-07 — Tenant IP allow-list and session policy

| Field | Value |
|---|---|
| Module | [`security`](../../docs/blueprint/modules/security/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | SECURITY-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/security/README.md`](../../docs/blueprint/modules/security/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Enforce per-tenant IP allow-lists and session timeout/MFA policy.

- **depends on**:
  - SECURITY-02
- **files**:
  - backend/app/modules/security/headers.py
  - backend/app/modules/security/session_policy.py
  - backend/tests/security/test_session_policy.py
- **steps**:
  - 1. Store ip_allowlist (CIDR list) and session_timeout_minutes, mfa_required in tenant_settings.
  - 2. Add middleware: if an allow-list is set and the client IP is outside it, return 403.
  - 3. Read the IP only from trusted proxy headers (configured hop count).
  - 4. Enforce idle timeout using session last-seen.
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
    - A session idle for 31 minutes with a 30-minute policy returns 401.
  - **unit**:
    - 10.0.0.5 in ['10.0.0.0/24'] is allowed; 10.0.1.5 is denied.
    - A spoofed X-Forwarded-For beyond the trusted hop count is ignored.
