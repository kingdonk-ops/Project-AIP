# Architecture decision records

ADRs override the blueprint (see precedence in [AGENTS.md](../../AGENTS.md)). Copy
[0000-template.md](0000-template.md) to add one.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-typescript-greenfield-rebuild.md) | TypeScript greenfield rebuild; Python only in the sidecar; translation table for Python-era text | accepted |
| [0002](0002-data-access-and-migrations.md) | Kysely; forward-only SQL migrations via node-pg-migrate; `withTenant` + `SET LOCAL`; DB roles | accepted, owner to confirm |
| [0003](0003-jobs-outbox-and-sidecar.md) | BullMQ jobs; Postgres outbox dispatcher; sidecar over HTTP | accepted |
| [0004](0004-repository-layout.md) | Canonical monorepo layout; field PWA and portal as Vite apps | accepted (field framework proposed) |
| [0005](0005-identity-architecture.md) | Keycloak brokers federation only; app issues all sessions; in-app SCIM | accepted, owner to confirm |
| [0006](0006-per-tenant-envelope-keys.md) | Per-tenant KMS envelope keys (reverses shared key) | proposed |
| [0007](0007-mvp-scope-and-strangler.md) | Walking skeleton → trimmed P0 → R1 "Kaefer live"; AIP keeps running | proposed |
| [0008](0008-entitlements-and-commercial-model.md) | One entitlement service; sales-led; contract billing at launch | proposed |
