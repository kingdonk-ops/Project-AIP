# OPS-12 — Operator console on its own origin and realm (ADR 0017)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | TENANCY-05, IDENTITY-04, OPS-07 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. ADRs: [0005](../../docs/adr/0005-identity-architecture.md), [0017](../../docs/adr/0017-company-systems-and-contract-link.md)
3. [`docs/blueprint/05-access-matrix.md`](../../docs/blueprint/05-access-matrix.md) (Super-admin account and the hand-edited column note)

## Spec

Serve every platform-operator page from a separate origin with its own Keycloak realm, WebAuthn and a network allowlist, so a routing mistake in the tenant app cannot expose platform controls.

- **files**:
  - infra/terraform/ (operator host, allowlist, separate WAF rule set)
  - config/keycloak/ (operator realm as code)
  - apps/web/src/routes/platform/ (operator routes only)
  - apps/api/aip/platform/access/operator.py (operator principal check shared by the API)
  - e2e/web/operator-console.spec.ts
- **steps**:
  - 1. Define a `platform-operator` realm in the realms-as-code directory: WebAuthn required, no self-registration, no federation to customer IdPs, short sessions.
  - 2. Serve `/platform/*` only from the operator host. The tenant app build contains no operator routes.
  - 3. The API accepts operator routes only with an operator-realm token; a tenant-realm token, even for a tenant admin, gets 403.
  - 4. Add a network allowlist at the edge and a separate rate-limit rule.
  - 5. Move any operator page still under `/admin/*` to `/platform/*`; tenant-admin pages stay under `/settings/*`.
- **acceptance**:
  - A tenant-realm token cannot reach any `/platform/*` API route.
  - The tenant app bundle contains no operator route.
  - Operator sign-in needs a WebAuthn credential.
- **tests**:
  - **integration**:
    - Tenant-admin token on `GET /api/v1/platform/tenants`. Expected: 403.
    - Operator-realm token on the same route. Expected: 200.
    - Search the tenant web build output for `/platform/`. Expected: no operator route component.
  - **e2e**:
    - Operator signs in with a virtual authenticator on the operator host and opens `/platform/tenants`. Expected: the register shows. The same URL on the tenant host returns 404.
