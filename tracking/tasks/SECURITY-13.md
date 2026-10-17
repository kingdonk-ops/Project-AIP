# SECURITY-13 — Least-privilege aip_readonly

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`security`](../../docs/blueprint/modules/security/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DATABASE-07 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/security/README.md`](../../docs/blueprint/modules/security/README.md)
3. ADRs: 0012
4. [review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md), the finding named below

## Background

[review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md) finding **M3**. Every policy keys on `current_setting('app.tenant_id', true)`, which any role can set
with `set_config`. `aip_readonly` has SELECT on `user_session` (ip, user_agent, kc_sid), `app_user`, `auth_event`,
`audit_log`, `security_audit_events` and `breach_incidents`. `db/bootstrap/00_cluster.sql:66` says "RLS limits what it
reads", which is untrue for a role that runs arbitrary SQL.

## Spec

The reporting login cannot read other tenants' PII or session metadata.

- **files**:
  - db/bootstrap/00_cluster.sql
  - a migration revoking the grants
  - db/ reporting views or SECURITY DEFINER aggregates
  - docs/adr/0012-runtime-roles-in-cluster-bootstrap.md (amendment)
- **steps**:
  - 1. Revoke `aip_readonly` on the session, auth and PII tables.
  - 2. Serve reporting through security-barrier views or `SECURITY DEFINER` aggregates that pin `search_path` and expose no PII.
  - 3. Amend ADR 0012: for roles that run arbitrary SQL, RLS is advisory.
  - 4. Fix the `00_cluster.sql` comment.
- **acceptance**:
  - `aip_readonly` with `set_config('app.tenant_id', <other tenant>)` reads no row of the listed tables.
  - Reporting still works through the new views.
- **tests**:
  - **integration**:
    - as `aip_readonly`, set another tenant's id and select from `user_session` → permission denied
    - grant posture check → `aip_readonly` has none of the revoked grants
