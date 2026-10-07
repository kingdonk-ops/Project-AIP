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
