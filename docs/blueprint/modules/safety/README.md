# Safety & HSE (`safety`)

- **Group:** Safety & compliance
- **Phase:** P2

What it is
A basic incident, near miss and observation reporting module, with an optional advanced HSE pack that can be switched on per site for sites that need it. The owner's decision is that the basic module is the standard offer and the advanced pack is normally disabled. Not built in AIP yet (suggested phase P2). Competitors (SafetyCulture, HammerTech, Procore Safety, Sitemate, Cority, Intelex, Riskcloud and others) cover this well, so the module stays minimal, runs corrective actions on the shared issues/CAPA engine and integrates with the customer's own HSE system (for example Kaefer's) rather than competing with it.

What it does
Records incidents, near misses and observations with photos, location and asset, scores risk (likelihood x consequence from a configured matrix), tracks corrective actions and the regulator-notifiable timeline, and masks injury and health information at field level. The advanced pack adds permit to work, JSA/JHA, toolbox talks, PPE issue, HSE audits and KPIs. When the advanced pack is disabled for a site, the permit gate is skipped and the basic module continues to work alone.

Features
- Incident, near miss and observation reports with photos, location and asset
- Risk scoring and corrective actions (shared issues/CAPA engine)
- Investigation form with root cause and contributing factors
- Regulator-notifiable flag and a notification clock with jurisdiction rules (WA, NZ, UK) and deadlines
- Field-level masking of injury and health information under a separate permission, with limited exports and restricted offline caches
- Mobile quick report that works offline, with a client UUID for idempotent sync
- Link or reference to the client's or employer's HSE system record (reference and status), to avoid double entry
- Asset and scope context on observations (for example CUI hazards, asbestos in insulation, confined space), shown in the scope pack
- Stop-work flag that places a hold on linked tasks or ITP steps
- Advanced pack per site: permit to work with competency gate and simultaneous-operations conflict view, JSA/JHA, toolbox talks with attendance, PPE issue register, HSE audits (reusing qms_audits with audit_type = hse), CAPA
- Lagging and leading KPIs: TRIR, LTIFR, observations per 200k hours, with an hours-worked feed from resources

Interactions
- Form & template designer: permits, JSAs and checklists are templates
- Issues, NCRs & corrective actions: corrective actions; an NCR is raised only where an incident reveals a quality failure
- Certificates, competency & calibration gate: permit holder competencies
- Dashboards & KPI reporting: HSE KPIs
- Site diary & field reports: incidents appear in the day's diary and can pre-fill entries
- Temporary works register: permit to load/strike interplay
- Inspections and tasks: can check permit state and stop-work holds before work starts
- Notifications: serious incident raised, notifiable deadline approaching, action assigned or overdue, permit expiring, competency invalid for permit holder, investigation assigned

Data
- hse_site_settings: per tenant and project, advanced_pack_enabled (default false), risk_matrix (JSONB), notification_rules (JSONB)
- Incident/observation record: report_kind, incident_type, severity, occurred_at, location (point) and location_text, asset_id, description, damage_details, likelihood, consequence, computed risk_score, is_regulator_notifiable, status, reported_by, diary_entry_id, client_uuid
- Also risk_assessment, regulator_notification, and advanced tables permit, jsa, toolbox_talk, ppe_issue
- Reuses assets, issues, tasks, certificates, documents, consumable_issuances
- Sensitive columns are tagged for masking, with stricter RLS; advanced tables are reachable only when the site flag is on
- Retention under Privacy Act and legal-hold rules; legal hold blocks deletion
- Configuration, not code: risk matrix, types and severities, notification rules and timelines, templates, enablement per site, KPI formulas and hours basis, masking fields and roles, retention periods

Pages
- Incident register (/projects/:projectId/safety): filters, Quick report button, bulk actions (export masked, assign investigator, close)
- Report incident or observation (/safety/new): simplified mobile variant, live risk band
- Incident detail and investigation (/safety/:reportId): WorkflowBar, regulator timeline banner, tabs for summary, risk, location/asset/diary, people (masked), injury details (restricted), photos, investigation, corrective actions, audit trail
- Action list and, when enabled, advanced sub-tabs for permits (live board), JSAs, toolbox talks and KPIs
- Permissions: safety.view for the register; any site user can report; injury fields need safety.sensitive.read
- Settings: enable advanced pack per site, risk matrix, types, notifiable criteria, masking roles, hours source, retention and legal hold, escalation recipients

Decisions and notes
- Owner: basic module, with HSE Advanced as a basic system for sites that need it, usually disabled
- Per-tenant/site module toggles; safety and advanced share one store, not separate ones
- All six advisor suggestions were accepted by the owner
- Do not out-build specialist permit-to-work tools; integrate or import permit and induction status where useful

Open questions
- Which jurisdiction timelines and notifiable criteria apply first beyond WA?
- Which hours-worked basis applies for TRIR and LTIFR?
- Retention periods for incident records?

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
