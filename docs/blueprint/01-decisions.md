# Owner decisions

> Owner decisions override advisor text anywhere else in the blueprint.
> Conflicts *between* decisions are resolved in `docs/adr/` — check there first.


- **Continue AIP FastAPI or rebuild in TypeScript**: TypeScript rebuild
- **Identity provider**: Keycloak self-hosted
- **Offline field app: PWA or native**: PWA first
- **Pooled or siloed tenancy at launch**: Pooled only at launch
- **Form and rules expression language**: JSONLogic
- **PDF rendering engine**: Gotenberg (Chromium)
- **Search backend**: Postgres FTS + pgvector
- **RFI naming: hold point or request for information**: Keep AIP's RFI as hold point
- **Scope Portal v1 split view or v2 unified grid**: v2 unified grid
- **Inspection status vocabulary**: Neutral codes with the AIP stages as defaults
- **Access-method vocabulary**: Split MEWP and Ladder, tenant-editable list
- **Local authentication: build or buy**: Build in-app on libraries
- **Authorisation engine**: Custom policy service plus RLS
- **Production hosting target**: AWS ECS Fargate in Sydney
- **Infrastructure as code tool**: Terraform/OpenTofu
- **PDF and markup viewer**: PDF.js plus Konva
- **External e-signature provider**: Defer external provider
- **AI model provider and region**: Direct model vendor API
- **Orm and migration approach**: Keep Alembic raw SQL with templates
- **Tenant-set and encryption key scheme**: Shared key with tenant prefixes
- **Background job runner**: Redis queue (arq or Celery)
- **Launch market terminology packs**: en-AU only, others as data later
- **Compliance certification sequence**: SOC 2 Type I then ISO 27001, IRAP later
- **Frontend framework: React with Vite or Next.js**: Next.js
- **External portal delivery**: Separate build on its own origin
- **Portal access scope at first release**: Read-only plus hold-point witness and counter-sign
- **Asset tag import master and edit rules**: Platform as master
- **Reporting read-model mechanism**: Snapshot tables with tenant_id and RLS

## Errata (2026-10-07)
<!-- errata: keep on regeneration -->

The owner lines above are kept as issued. Where an ADR changes or reconciles one, the ADR wins (see
[`docs/adr/`](../adr/README.md)); this block records which.

- **Continue AIP FastAPI or rebuild in TypeScript** ("TypeScript rebuild") → superseded by [ADR 0001](../adr/0001-greenfield-python-backend.md): greenfield build, Python backend (FastAPI), TypeScript frontends; AIP code, schema and data not used (owner, 2026-10-07).
- **Background job runner** ("Redis queue (arq or Celery)") → superseded by [ADR 0003](../adr/0003-jobs-outbox-and-sidecar.md): Procrastinate on Postgres (owner answered "Postgres-based", 2026-10-07; accepted).
- **Frontend framework** ("Next.js") → superseded by [ADR 0004](../adr/0004-repository-layout.md): Vite for all three apps (web, field PWA, portal) (owner, 2026-10-07; accepted).
- **Tenant-set and encryption key scheme** ("Shared key with tenant prefixes") → [ADR 0006](../adr/0006-per-tenant-envelope-keys.md) proposes one AWS KMS key per tenant (proposed; owner to confirm).
- **Identity provider** ("Keycloak self-hosted") plus **Local authentication** ("Build in-app on libraries") → reconciled by [ADR 0005](../adr/0005-identity-architecture.md) rev 2: Keycloak handles all staff sign-in (SSO, password, MFA); the backend issues sessions and builds field PIN, portal links and SCIM (owner, 2026-10-07; accepted).
- **Orm and migration approach** ("Keep Alembic raw SQL with templates") → consistent with [ADR 0002](../adr/0002-data-access-and-migrations.md): forward-only Alembic raw-SQL revisions with SQLAlchemy Core on asyncpg (accepted).
