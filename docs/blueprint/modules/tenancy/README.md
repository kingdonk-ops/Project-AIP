# Tenancy, organisations & data residency (`tenancy`)

- **Group:** Foundations & architecture
- **Phase:** P0

What it is
The model for separating customers and their clients, and for deciding where their data physically lives. It defines the scope chain Tenant > Organisation > Project > Team > Asset subtree. Kaefer is a tenant; Rio Tinto is a client organisation inside it; projects are campaigns over assets. Tenant, organisation and project stay separate levels because contractors and clients both need scoped access. It must be settled now because it cannot be retrofitted across the whole module set. It builds on the existing AIP product, whose schema already has organisations > projects > sites, with org isolation enforced only in application code (Phase 24).

What it does
At launch the platform runs pooled only: a shared database with RLS. The design keeps the schema identical for a siloed deployment (own database, KMS key and bucket) so one can be added later for IRAP or mining clients from the same codebase and pipeline. Data stays in-region: Australia first (Sydney, ap-southeast-2), with London (eu-west-2) and Singapore (ap-southeast-1) stacks later. NZ is served via Sydney with contract wording. Client organisations can share an asset record without seeing each other's commercial data. Residency stacks and silos change in IaC variables, not in module code.

Features
- Pooled stack: tenant_id plus RLS on every table, with tenant-scoped Redis keys, queues, S3 prefixes, search indexes and embeddings (key builders)
- Application runs as a non-owner database role without BYPASSRLS; FORCE RLS on; tenant set per request via SET LOCAL app.tenant_id and fails closed if unset; the tenants table is protected by id = app.tenant_id
- Siloed stack (later): one deployment per customer from the same codebase and pipeline
- Per-tenant KMS keys for crypto-shredding on offboarding, tested against legal-hold exceptions. Note the owner chose a shared key with tenant prefixes as the tenant-set and encryption key scheme; how this reconciles with per-tenant KMS keys is open
- Region per deployment: ap-southeast-2 first; eu-west-2 and ap-southeast-1 later; NZ via Sydney with contract wording
- Client organisations (types: owner, client, subcontractor)
- Shared asset record with party-scoped field visibility (Rio Tinto sees status and evidence, not Kaefer rates), using visibility profiles, optional expiry, revoke and preview as organisation (accepted)
- Tenant settings: branding, terminology, modules enabled, retention defaults
- Tenant provisioning wizard and script: region, template pack, terminology set, admin invite, sample data (accepted)
- Offboarding workflow: full export, legal-hold check, crypto-shred, and a signed deletion certificate (accepted)
- Customer-approved, time-boxed support access with banner and audit entries (accepted)
- Activate project-scoped roles (user_roles.project_id, currently unused) and replace application-level org joins with RLS (accepted)
- Per-tenant quotas and noisy-neighbour limits on jobs, storage and API calls (accepted)
- Cross-tenant and IDOR test suite in CI before any module ships, generated from the route and table catalogue; CI fails if any new table lacks tenant_id or a policy

Interactions
- Roles, permissions & teams: membership and roles are evaluated inside the tenant scope; membership rows carry a role plus optional asset-subtree scope; authorisation is a custom policy service plus RLS
- Database & schema conventions: implemented as RLS policies
- Operations, hosting & deployment: AWS ECS Fargate in Sydney, Terraform/OpenTofu
- Security & compliance programme: isolation is the first control auditors test
- Terminology dictionary & localisation: each tenant has its own vocabulary; en-AU only at launch

Data
- tenants (id equals tenant_id, name, slug, deployment_shape pooled or siloed, region_id, kms_key_ref, status provisioning/active/suspended/offboarding/offboarded, soft delete), deployment_regions (code, label, in_country_only), Organisation (type owner/client/subcontractor, registration number), TenantSettings, TenantModule, OrgAssetShare, plus offboarding and deletion-certificate records and support-access grants with audit entries
- tenant_id added to every existing AIP table, backfilled by migration, with FORCE RLS and policy USING (tenant_id = current_setting('app.tenant_id')::uuid), failing closed when unset
- Reuses organisations, projects, sites, assets, documents, users, user_roles
- Components: tenancy module (models, schemas, context, rls, policies, service, router, offboarding, keys), tenant_id RLS backfill migration, tests test_isolation and test_rls_catalog (asserts RLS enabled and forced, no BYPASSRLS role)
- Settings: branding, terminology set, enabled modules, retention defaults, region (set at provisioning), visibility profiles, support access policy and maximum duration, quota defaults, siloed stack requirement by customer type
- The schema works identically in pooled and siloed shapes

Pages
- Tenants register (/platform/tenants), operator only
- Tenant provisioning wizard (/platform/tenants/new)
- Tenant settings (/settings/tenant): profile and region, branding, terminology, modules, retention, quotas and usage, KMS key and residency, support access history
- Organisations (/settings/organisations) and organisation detail (/settings/organisations/:id)
- Asset sharing: rules for what each party sees on a shared asset
- Offboarding and support-access approval screens
- Notifications: tenant invite, asset shared, share expiring in 7 days, support access events, quota at 80% and 100%, offboarding steps and certificate, cross-tenant CI test failure

Decisions and notes
- Owner decisions: pooled only at launch; custom policy service plus RLS for authorisation; AWS ECS Fargate in Sydney; Terraform/OpenTofu; shared key with tenant prefixes; en-AU only at launch; Keycloak identity.
- Owner accepted all six scout suggestions listed under Features.
- Security advises that pooled RLS is the biggest single risk for Rio Tinto and government clients, so state when a customer is required to use a siloed stack once one is offered.
- Background workers and caches are the usual leak path, so every cache, queue, search index, S3 prefix and embedding is tenant-scoped.
- Crypto-shredding must respect legal-hold exceptions.
- Isolation tests run in CI as a gate.

Open questions
- Which customer types must use a siloed stack (for example IRAP or Rio Tinto direct), who decides, and when it is built given pooled-only at launch?
- How per-tenant KMS crypto-shredding fits with the decided shared key with tenant prefixes.
- Whether NZ customers ever require in-country storage.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
