# Projects, sites & classification (`projects`)

- **Group:** Identity, access & tenancy
- **Phase:** P0

What it is
A project is a scoped campaign of work (campaign, shutdown, remediation package, new build) that references assets many-to-many rather than owning them, so asset history survives across projects. Projects and the sites they run on sit in the Identity, access & tenancy group (suggested phase P0). The module is deliberately thin and its data model drives every permission check, so it should be frozen early and kept small. It is separate from tenant and organisation, and it does not own asset data. Projects serve as campaigns for now.

What it does
Creates and manages projects with code, name, client organisation, site, region, timezone, currency and status (draft, active, closing, archived). Links projects to a tenant-owned asset tree through a scope baseline. Applies a tenant-configured work-type classification that decides which approvals, ITP templates, documents and workflows apply. Enforces project scoping on every list and query, and gates archive behind a closeout checklist. Differentiator against project-centric competitors (Procore, ACC, Aconex, InEight, Primavera Unifier, Buildertrend, Fieldwire): asset history does not fragment across projects, and terminology and regional presets (AU, NZ, UK, Asia) are per tenant.

Features
- Project CRUD, edit and archive; project code unique per tenant (e.g. L592, ICHTHYS-KIPS)
- Header project switcher persisted per user; every list scoped to the selected project
- Project-scoped query enforcement as a platform default, with a visible 'all projects' override for permitted roles (needs a tenant-level permission)
- Sites under projects with GPS location; hidden system site per project for the hierarchy
- Project membership and roles (project-scoped), with default roles for new members
- Project participant directory with party role (client, principal contractor, subcontractor, third-party inspector), driving portal grants, visibility and routing
- Project-asset scope baseline with scope-change history (with reason), giving a baseline versus current view and diff export for variations and reporting as remediation scope grows
- Tenant-configurable work-type classification (e.g. remediation, shutdown, CUI campaign, new build, repair, maintenance) selecting required approvals, ITP templates, documents and workflows; impact preview and recalculation event when classification changes; seeded starter content, tenant-editable
- Project and campaign templates by work type carrying ITP sets, forms, roles and approval chains; instantiate a project from a template
- Per-project numbering schemes for records (inspections, NCRs, RFIs) with client prefixes
- Project settings: currency, units, calendar, retention overrides (within legal hold limits), enabled modules, terminology overrides (e.g. Work Pack versus Job)
- Project closeout checklist, assembled from checks registered by other modules, that blocks archive until open holds, NCRs and certificates are resolved; waivers also write to the audit module; external access auto-expires on close
- Project list bulk actions: export CSV, change work type with impact preview, apply template settings, archive only when closeout is complete
- Notifications: added to or removed from project, scope change added, classification changed and requirements recalculated, closeout blockers outstanding, archived or reopened, portal participant invited or access expiring
- Project dashboard entry point

Interactions
- Asset hierarchy & registers: projects are scoped campaigns over assets; every other module's tables carry project_id
- Roles, permissions & teams: project-scoped roles; teams for visibility; membership defaults; project.* permissions registered in the central catalogue
- Scopes of work (RSW), disciplines & tasks: scopes of work belong to a project
- Dashboards & KPI reporting: project dashboards
- Handover, data books & submissions: project closeout; required documents feed closeout and documents
- Inspections and ITP: default ITP template sets; compliance rule sets; review authority receives required approvals
- Client & subcontractor portal: participant directory drives grants
- Events emitted: project.created, project.closed, settings.changed, consumed by validation, approval routes, saved views, integrations, onboarding and cases

Data
- project: code, name, client organisation, site, region, timezone, currency, status, classification, template, closed_at
- site: name, code, GPS location, timezone, system flag, soft delete
- project_asset: asset_id, scope, baseline status, plus scope-change history
- project settings: only overrides of tenant defaults (terminology overrides, numbering schemes, enabled modules, validation rule sets, retention overrides)
- classification: route definition, classifier values, requirement bundle (required approvals, ITP templates, documents, workflows)
- project template: work type, ITP sets, forms, roles, approval chains
- membership and participant directory with party role
- All tables carry tenant_id with RLS

Pages
- Project list and setup wizard: portfolio table (code, name, client, site, work type, region, status, open holds, open NCRs, updated) with card toggle, filters and quick-view drawer; wizard steps for basics, site and region, scope, members, numbering and modules, review with required-items preview
- Project dashboard and detail: header and status, overview, KPI strip, tile grid, linked assets panel, members summary, activity and scope-change history
- Project settings with terminology editor
- Asset scope picker using the hierarchy tree (split view)
- Classification wizard, admin route designer and resulting required-items checklist
- Closeout checklist
- Placed under Projects and Planning in navigation

Decisions and notes
- Built in AIP: GET/POST /projects; header Projects switcher replacing the cosmetic site switcher (TASKS 46); ProjectContext shared by header and tree.
- Deferred in AIP: project edit/archive, per-project membership, scoping all queries to the selected project (now accepted as a platform default).
- Classification is tenant-configured, not a fixed list; the original fixed work-type list (reconstruction, capital repair, re-equipment, demolition, change of use) is dropped as geared to Russian-style regulation. Cost-classification standards such as DIN 276 or GAEB are dropped as irrelevant.
- Accepted suggestions: templates by work type, scope baseline with history, closeout gate, participant directory, per-project numbering, scoped query enforcement.
- Advisor recommendation (not yet owner-confirmed): projects serve as campaigns, with a nullable parent_project_id added later if needed.

Open questions
- Split of regional settings and validation config: the architecture advisor places them with the tenant or asset, the feature designer in project settings. Data advisor recommends tenant defaults with project overrides only; owner has not decided.
- Whether a separate campaign or work-pack entity is needed beyond the project, or whether projects serve as campaigns.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
