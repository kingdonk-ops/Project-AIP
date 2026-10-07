# Users, sign-in & SSO (`identity`)

- **Group:** Identity, access & tenancy
- **Phase:** P0

What it is
Users, sign-in and SSO manages user accounts, invitations, profiles and authentication for the platform. It covers four user classes: staff (SAML/OIDC SSO with SCIM and MFA), non-SSO customers (email + password + MFA), field and external users (single-use magic links or PINs with narrow scope), and system integrations (OAuth client credentials). Suggested phase: P0. Tenant, organisation and role mapping must be settled here before any other module is built.

What it does
It provides identity, sessions and policy checks to every other module. SCIM deprovisioning revokes sessions, API keys, magic links and portal access within minutes, in one transaction, and emits a user.deactivated event. Every sign-in and privilege change is written to the tamper-evident audit log. The four user classes have distinct session policies and assurance levels. SSO-managed users cannot fall back to password login.

Features
- SSO via WorkOS (SAML 2.0, OIDC: Entra ID, Okta, Google) with a per-customer admin portal
- Domain claim and SSO enforcement per tenant that disables password login for SSO-managed users (accepted)
- SCIM provisioning with group-to-role mapping and no implicit privilege escalation; SCIM deprovisioning tested end to end against a time target
- MFA (TOTP/WebAuthn) enforced for local accounts and for privileged roles even under SSO; MFA recovery no weaker than the MFA itself
- Passwords hashed with Argon2id
- Magic link / PIN for field users: single-use, 15-minute tokens, hashed at rest, lockout after 5 attempts, device binding, click-through POST so email scanners do not consume tokens
- Shared-device field mode with PIN quick-switch, auto-lock and per-user offline data encryption; sign-off attribution stays individual (accepted)
- Sponsor-owned external accounts with a named internal sponsor, automatic expiry and periodic re-confirmation (accepted)
- Invite flow without the seed script; accept invite; set password
- Profile page: name, contact, competencies, signature image, notification preferences
- Competency and signature capture on the profile, bound to e-sign step-up (re-authentication at hold-point sign-off) (accepted); competencies stay in certificates and the eligibility gate, and the profile only links to them
- Short-lived access tokens (15 min) with rotating refresh tokens (30 days) and a server-side, revocable session table, replacing the HS256 single JWT (accepted)
- API keys for integrations: scoped, hashed, expiring, with per-key audit; OAuth client credentials for system integrations
- Login disambiguation across organisations
- Break-glass admin access with time-boxed elevation and dual approval; login-as uses this pattern (accepted); break-glass accounts are audited
- Admin tools (deferred): set password, email login link, login-as with audit, copy user

Interactions
- Roles, permissions and teams: roles and permissions are applied after sign-in; SCIM groups map to roles and teams; user.deactivated is consumed by teams, approval routes (reassign pending steps) and integrations
- Tenancy, organisations and data residency: users belong to a tenant and organisation; tenant, organisation and project membership are separate levels so clients such as Rio Tinto can have scoped access to Kaefer data
- Certificates, competency and calibration gate: a person's qualifications live on their profile/register record
- Client and subcontractor portal: external users sign in through the same service
- Audit trail, activity and timeline: every sign-in and privilege change is logged (the hash-chained store belongs to the audit module)
- Projects: read for membership scope

Data
- User (one row per person per tenant), tenant membership, organisation
- Role and role assignment (project, team or asset-subtree scope)
- API key (hashed, scoped, expiring)
- Session (server-side)
- Magic-link token (single-use, 15 minutes, hashed)
- MFA credential and break-glass grant
- External account sponsor and expiry
- Audit event
- Session timeouts and the SCIM time target are held as policy data, not code

Pages
Settings > Users, SSO and SCIM:
- User directory table with role, team, MFA status and SCIM status, plus a detail drawer for access scope
- SCIM sync status panel
- Role and permission matrix
- MFA and session policy
- API key management
- Profile page
- Sign in, magic link confirm and accept invite pages

AIP status: JWT login (HS256, no refresh), users and roles admin, deactivation, invite a user (TASKS 41), profile page (9.1) and login-by-email cross-org fix (42) are built. The profile signature card exists but capture is deferred until a report engine exists.

Decisions and notes
- Do not build SAML, SCIM or MFA from scratch. The scope doc chose WorkOS, which covers SAML, OIDC, SCIM and the admin portal. Magic links, PINs and device binding are custom code in FastAPI. Keep a local profile and membership table plus your own session, API-key and magic-link layer, so swapping provider is confined to the WorkOS adapter.
- The spec target of OIDC via Keycloak (E1-S2) is superseded by the WorkOS choice in the scope doc.
- The owner accepted the six feature suggestions listed above.
- Org-level and project-level roles are needed, with external parties (clients, subcontractors) as first-class members.
- The differentiator is one policy layer covering tenant, organisation, project, team and asset scope, with hard revocation on deprovision.

Open questions
- WorkOS versus self-hosted Keycloak: the architecture advisor favoured Keycloak for IRAP and residency constraints, while the other advisors favoured WorkOS. The scope doc chose WorkOS but residency needs confirming.
- Time target for SCIM deprovisioning (currently stated as within minutes) is not defined.
- Idle and absolute session timeouts per user class are not set.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
