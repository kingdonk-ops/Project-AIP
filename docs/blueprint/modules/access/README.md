# Roles, permissions & teams (`access`)

- **Group:** Identity, access & tenancy
- **Phase:** P0

What it is
The single authorisation layer for the platform: who can see and do what, across tenant, organisation, project, team and asset subtree. It is one policy model evaluated once (CASL or OpenFGA style) and backed by Postgres row-level security (RLS) or query filters, so enforcement lives in the data layer and not only in controllers or the UI. Deny by default, failing closed. Teams and visibility rules are part of this layer, not a separate module or visibility system. Suggested phase P0.

What it does
Roles carry permissions from a single catalogue. Users get project-scoped roles and optional per-user overrides. Team membership limits visibility of records (for example a subcontractor team sees only its own records). Asset-subtree scope limits a user or team to part of the asset tree. Discipline and method qualification determine who may inspect or sign. The same rules apply uniformly to UI, API, search, dashboards, exports, files, comments and AI features, because aggregate and search modules otherwise bypass module-level checks. Subcontractor teams never see commercial records (variations, claims, supplier pricing, rates) belonging to other parties, which is the gap in Procore, ACC and Aconex, whose record-level visibility is coarse.

Features
- Permission catalogue per module and ability (AIP has 23 today), one source of truth for routes and UI; each module registers its abilities, gaining enforcement, tests and matrix coverage automatically
- Custom roles: create, edit, delete; default roles inspector, supervisor, engineer, manager, client
- Per-user permission overrides on top of roles
- Project-scoped roles and a per-project permission matrix
- Teams: membership, team-based visibility of records (for example Kaefer insulation crew, MEP subcontractor, client reviewers)
- Visibility rules per team: module or entity type, asset subtree, and field masks
- Discipline-scoped permissions (who may inspect or sign which discipline)
- Discipline-and-method qualified sign-off tied to competency, linked to the certificate gate (for example only UT-qualified staff sign UT inspections) rather than relying on role names
- Asset-subtree scoping on membership, with inheritance rules and explicit exclusions (access to a unit but not a sensitive system within it)
- Field masking policies per party: hide rates, internal NCR notes and personal data from client or subcontractor teams
- Effective-access explorer showing why a user can or cannot act on a record (role, team, subtree, discipline)
- Time-boxed delegation and acting-in-role with start/end dates and audit, so no shared credentials
- Permission-matrix export and automated tests generated from the catalogue
- Quarterly access review export; all privilege changes audited
- UI hides or disables actions the user can't perform instead of failing with 403
- Bulk team assignment from SCIM groups; SCIM mapping cannot implicitly grant tenant admin
- IDOR testing on every ID-addressed endpoint, especially files, comments, search results, dashboards and exports

Interactions
- Users, sign-in & SSO: applies to signed-in users; SCIM groups feed team assignment
- Tenancy, organisations & data residency: evaluated within tenant scope
- Client & subcontractor portal: external users get narrow roles and masked fields
- Search, retrieval & saved views: results filtered by the same rules; team scoping supplies saved view sharing
- Dashboards & KPI reporting: dashboards respect permissions
- Approval routes: team scoping supplies step assignment; approvals for overrides and custom roles reuse the approvals engine
- Certificates: competency and expiry feed qualified sign-off
- AI governance: retrieval uses this policy layer at query time
- Emits team.membership_changed to invalidate permission caches

Data
- Permission catalogue entry (module, ability, privileged flag requiring MFA and approval to grant)
- Role (stable internal code, display name via terminology key), role permissions, project-scoped role assignment, per-user override
- Team (project, organisation, type), team membership
- Visibility rule (module or entity type, asset subtree, exclusions, field masks)
- Discipline and method grants tied to competency
- Delegation (delegator, delegate, role, start, end)
- Audit log of privilege changes
- Scope tables denormalise the asset path (ltree) so RLS predicates avoid joins; a trigger refreshes them when assets move

Pages
- Settings > Organisation and Teams: team list on the left; members and visibility rules (modules and asset subtrees) on the right
- Team member editor and visibility rule builder with a preview of what the team can see
- Users & Roles with permission matrix per project
- Role assignments with subtree picker and exclusions
- Effective-access explorer
- Access review and matrix export

Decisions and notes
- Built in AIP: granular permission catalogue, role management, per-user overrides (TASKS §38); discipline grants admin-managed on Users & Roles (§47)
- Deferred in AIP: per-project permission matrix, discipline-scoped inspection permissions, Login As, audit modal
- Owner accepted: effective-access explorer, competency-qualified sign-off, subtree inheritance with exclusions, time-boxed delegation, matrix export with generated tests, per-party field masking
- Single policy layer, enforced in RLS or query filters, not per controller; changes to evaluation happen only in the policy and RLS code
- Overrides and custom roles risk privilege creep, so they need approvals and periodic access reviews (SOC 2)

Open questions
- Which engine: CASL or OpenFGA? (The schema supports either as a source of tuples.)
- Should override and custom role changes require a formal approval workflow, and who approves?
- Is Login As (view as user) in scope, or is the effective-access explorer sufficient?

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
