# Client & subcontractor portal (`portal`)

- **Group:** Identity, access & tenancy
- **Phase:** P2

What it is
A separate, narrow view for people outside your company: clients (such as Rio Tinto), subcontractors, suppliers and consultants. It gives scoped external access so they see and act only on what has been explicitly shared with them. It builds on AIP's existing client_review lifecycle stage and the PRD 'Client' role (read-only assets, reports, issues and documents in scope). Suggested phase: P3, built only after internal authorisation is proven. It is the largest exposure of client data and the likeliest path to cross-tenant or cross-team exposure.

What it does
External users sign in by magic link to a separate origin with its own session policy. They see only records shared with them: assets, reports, inspections awaiting their sign-off, documents and issues in their scope. Clients can counter-sign (client review stage), comment, see upcoming hold and witness points and confirm attendance or waive with notice. Subcontractors can respond to NCRs and upload evidence. No admin APIs are exposed. Sharing is explicit, not inherited visibility. Commercial modules are hidden from non-commercial parties. Start with read-only client access, then add actions.

Features
- Separate origin and app instance, WAF rate limiting, no admin endpoints, narrow API surface
- Client review and counter-sign of inspections (AIP's client_review stage, requires_client_sign_off per template)
- Hold-point witness booking: client sees upcoming hold/witness points and confirms attendance or waives with a notice period; notification when notice period is ending and when a waive is recorded
- Read-only asset, report and document access within scope
- Client-side read-only asset condition dashboard with defect trends by area
- Subcontractor responses to issues/NCRs with evidence upload through the uploads module under strict upload controls
- Subcontractor onboarding gate: valid company and personnel certificates required before they can submit work (extends the certificate hard-block to external parties, reads certificates via eligibility)
- Share packs: time-limited, read-only bundles of reports and certificates for an asset or scope, usable without a full portal account, with expiry, revocation and access log
- Download watermarking and view-only mode with a per-grant download policy and default watermark text
- Per-client branding and terminology (logo and client vocabulary) applied to the portal and notification emails
- 'Needs my action' inbox on the portal home
- Notification emails with deep links; magic links use scanner-safe click-through (POST confirm), hashed single-use short-lived tokens, device binding and PIN lockout with admin alert
- Invitation approval by a named internal owner; automatic expiry of external access when a project closes; grants revoked on project removal (or SCIM)
- Full audit of every external view, download and action, written to the tamper-evident audit log
- Per-tenant on/off (disabled by default); configurable session lifetime, idle timeout, rate limits and visible modules

Interactions
- Users, sign-in & SSO: magic-link sign-in
- Roles, permissions & teams: narrow external roles and the same authorisation layer with an external-user class, fed by portal grants
- Inspections, ITPs & hold points: client sign-off step and witness booking
- Issues, NCRs & corrective actions: subcontractor responses
- Document library & control: shared documents
- Certificates: onboarding gate
- Notifications: magic links and emails
- Terminology layer: client-specific vocabulary
- Projects: participant directory with party role drives grants
- Reads projects, users and contacts; may later expose transmittals, RFIs, submittals, punchlist, defects liability and closeout
- Writes responses, comments and uploads back through uploads and file comments; triggers approvals through approval routes

Data
- PortalUser: linked to contact, company and scope; email unique per tenant; status (invited, pending approval, active, suspended, expired); invited_by, approved_by (named internal owner), expires_at, optional external IdP subject for later SSO
- PortalGrant: project, asset subtree, module, action, plus download policy
- PortalSession: magic link or PIN credentials stored as hashes, TTL, consumed_at, failed attempts, locked_until, device binding
- PortalAuditEvent (also mirrored into the main audit chain)
- Share pack: time-limited bundle with expiry and contents
- Branding settings per client: logo, terminology
- Postgres RLS enforced on all of these, reusing the same RLS and external-party model as internal tenancy (tenant_id on every table); UI filtering alone is not acceptable

Pages
- Portal home showing items awaiting my action
- Asset-tree view with status and documents
- Action pages: approve or counter-sign, respond, upload, confirm or waive witness
- Read-only asset condition dashboard
- Share pack viewer
- Internal admin screens: external users register with pending approvals tab (/admin/portal/users), invite form with grant builder, external user detail (profile, onboarding gate, grants, sessions and devices, audit trail, pending actions), share pack management, and portal settings with branding preview

Decisions and notes
- Owner accepted all six feature suggestions: witness booking, share packs, per-client branding and terminology, subcontractor onboarding gate, condition dashboard, download watermarking and view-only mode.
- Enforce RLS plus the central policy layer; no reliance on UI filtering.
- Separate session and rate-limit settings from the internal app; portal is a separate deployable calling other modules only through the policy service and events.
- Competitor gap this fills: asset-subtree scoping, so a client sees only its assets, inspection records and status, and subcontractors are blocked from commercial data. Magic-link flows, audit log and IRAP-ready controls are differentiators.
- Defer until internal permissions are proven.

Open questions
- Identity approach for portal users: in-app magic link and PIN only, or WorkOS SAML/SCIM for client enterprise SSO (about USD 125 per connection per month), with Keycloak only if self-hosting is required. Not decided.
- Whether the accepted features all land in P3 or are staged after the initial read-only release.
- Notice period defaults for witness waiving, and whether they are set per client or per ITP.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
