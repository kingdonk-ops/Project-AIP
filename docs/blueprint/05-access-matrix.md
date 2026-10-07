# Accounts, profiles and access matrix


- **access matrix**:

| Module | Super Admin | Tenant Admin | Project Manager | QA/QC Manager | HSE Officer | Supervisor | Inspector | Field Worker | Document Controller | Client Reviewer | Subcontractor | Auditor | API Client |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Architecture & module boundaries | admin | none | none | none | none | none | none | none | none | none | none | none | none |
| Tech stack | admin | none | none | none | none | none | none | none | none | none | none | none | none |
| Database & schema conventions | admin | none | none | none | none | none | none | none | none | none | none | none | none |
| Tenancy, organisations & data residency | admin | admin | view | none | none | none | none | none | none | none | none | view | none |
| Security & compliance programme | admin | view | none | view | view | none | none | none | none | none | none | view | none |
| Operations, hosting & deployment | admin | none | none | none | none | none | none | none | none | none | none | none | none |
| Design system & app shell | admin | admin | none | none | none | none | none | none | none | none | none | none | none |
| Testing & quality engineering | admin | none | none | none | none | none | none | none | none | none | none | none | none |
| Terminology dictionary & localisation | admin | admin | view | view | none | none | none | none | view | none | none | view | none |
| AI governance & data controls | admin | admin | none | view | none | none | none | none | none | none | none | view | none |
| Users, sign-in & SSO | admin | admin | view | none | none | none | none | none | none | none | none | view | none |
| Roles, permissions & teams | admin | admin | edit | view | none | none | none | none | none | none | none | view | none |
| Projects, sites & classification | admin | admin | admin | view | view | view | view | view | view | view | view | view | view |
| Client & subcontractor portal | admin | admin | approve | edit | none | none | none | none | edit | view | view | view | none |
| Asset hierarchy & registers | admin | admin | edit | edit | view | edit | create | view | view | view | view | view | create |
| Content types, item types & attributes | admin | admin | view | edit | none | none | none | none | view | none | none | view | none |
| Traceability graph: components, materials & certificates | admin | admin | edit | approve | view | edit | create | create | view | view | create | view | create |
| Scopes of work (RSW), disciplines & tasks | admin | admin | approve | edit | view | edit | view | view | view | view | view | view | create |
| Offline field app & sync | admin | admin | view | view | view | create | create | create | none | none | create | none | none |
| Form & template designer | admin | admin | view | admin | edit | view | view | view | view | none | none | view | none |
| Inspections, ITPs & hold points | admin | admin | approve | approve | view | approve | create | create | view | approve | create | view | create |
| Certificates, competency & calibration gate | admin | admin | edit | approve | edit | edit | view | view | edit | view | create | view | create |
| Issues, NCRs & corrective actions | admin | admin | approve | approve | approve | approve | create | create | view | create | edit | view | create |
| Punch list & defects liability | admin | admin | approve | approve | view | edit | create | create | view | create | edit | view | none |
| Quality roll-up & audits | admin | admin | view | admin | view | view | none | none | view | none | none | view | none |
| Rules & validation engine | admin | admin | view | edit | none | none | none | none | none | none | none | view | none |
| Commissioning | admin | admin | approve | approve | view | edit | create | view | view | approve | create | view | none |
| Report engine & published records | admin | admin | approve | approve | create | create | create | none | create | view | none | view | view |
| Safety & HSE | admin | admin | approve | view | admin | create | create | create | view | none | create | view | none |
| Temporary works register | admin | admin | approve | view | approve | edit | create | view | view | view | create | view | none |
| Site diary & field reports | admin | admin | approve | view | view | approve | create | create | view | view | create | view | none |
| Voice notes & phone log | admin | admin | edit | view | none | create | create | create | none | none | none | view | none |
| Site logistics & mobilisation | admin | admin | approve | view | view | edit | view | create | view | view | create | view | none |
| Equipment & fleet | admin | admin | edit | edit | view | edit | view | create | view | none | create | view | create |
| Stock, consumables & materials | admin | admin | edit | view | none | edit | create | create | view | none | create | view | create |
| Resources & crews (basic) | admin | admin | approve | view | view | edit | view | view | none | none | none | view | none |
| Schedule & look-ahead (basic) | admin | admin | approve | view | view | edit | view | view | view | view | view | view | view |
| Document library & control | admin | admin | edit | edit | create | create | create | create | admin | view | create | view | create |
| Markup, viewer & plan room | admin | admin | create | create | create | create | create | create | create | create | create | view | none |
| Workflow & approvals engine | admin | admin | approve | approve | approve | approve | view | none | approve | approve | view | view | none |
| E-signatures & tamper-evident records | admin | admin | approve | approve | approve | approve | create | create | approve | approve | create | view | none |
| Transmittals & correspondence | admin | admin | approve | view | none | none | none | none | admin | view | view | view | none |
| Inbound capture & connectors | admin | admin | view | none | none | none | none | none | admin | none | none | view | none |
| Upload & file processing pipeline | admin | admin | create | create | create | create | create | create | create | create | create | none | create |
| Comments, mentions & notifications | admin | admin | create | create | create | create | create | create | create | create | create | view | none |
| Meetings & AI minutes | admin | admin | approve | edit | create | create | view | none | view | create | create | view | none |
| RFIs & submittals | admin | admin | approve | approve | none | create | create | none | approve | approve | create | view | none |
| Interface management | admin | admin | approve | edit | none | edit | none | none | view | approve | create | view | none |
| Tasks, deadlines & my work | admin | admin | approve | create | create | approve | create | create | create | create | create | view | create |
| Supplier catalogue, requisitions & POs | admin | admin | approve | view | none | create | none | none | view | none | none | view | view |
| Cost items & schedule of rates (thin) | none | none | none | none | none | none | none | none | none | none | none | none | none |
| Change orders, variations & MOC (basic) | admin | admin | approve | edit | none | create | none | none | view | approve | create | view | none |
| Contacts & companies | admin | admin | edit | view | view | view | view | none | edit | none | none | view | view |
| Regional reference data packs | admin | admin | view | view | none | none | none | none | view | none | none | view | none |
| Handover, data books & submissions | admin | admin | approve | approve | view | edit | view | none | admin | approve | create | view | none |
| Service & maintenance | admin | admin | approve | edit | view | edit | create | create | view | view | create | view | create |
| Prefab & off-site manufacture | admin | admin | approve | approve | none | edit | create | create | view | view | create | view | none |
| Dashboards & KPI reporting | admin | admin | edit | edit | view | view | view | none | view | view | none | view | view |
| Audit trail, activity & timeline | view | view | view | view | none | none | none | none | none | none | none | view | none |
| Search, retrieval & saved views | view | view | view | view | view | view | view | view | view | view | view | view | none |
| AI assistant & agents | admin | admin | view | view | view | view | view | none | view | none | none | none | none |
| Integrations & webhooks | admin | admin | view | none | none | none | none | none | none | none | none | view | edit |
| Data import, export & backup | admin | admin | create | view | none | none | none | none | create | none | none | view | view |
| User-authored playbooks | none | none | none | none | none | none | none | none | none | none | none | none | none |

- **account types**:
  -
    - **limits**: Roles are assigned per project and optionally per team or asset subtree. SCIM deactivation revokes sessions, API keys, magic links and portal access within minutes. Only the IdP or SCIM can change identity attributes.
    - **name**: Staff SSO user
    - **sign in**: SAML 2.0 or OIDC SSO via WorkOS, with SCIM provisioning and deprovisioning. MFA is enforced at the IdP, and the platform re-checks that the assertion carries an MFA claim.
    - **who**: Employees of the tenant (e.g. Kaefer inspectors, supervisors, managers, document controllers) who sign in through the company identity provider.
  -
    - **limits**: Needs an explicit tenant policy to be enabled. Local accounts are reviewed quarterly, and a tenant with SSO enabled can restrict local login to named break-glass admins only.
    - **name**: Local account user
    - **sign in**: Email and password with mandatory MFA (TOTP or WebAuthn). Includes breached-password checks, lockout and rate limiting, and a short session lifetime.
    - **who**: Staff or customers whose organisation has no IdP, plus break-glass tenant admins.
  -
    - **limits**: Scoped to named projects, sites and modules (diary, pre-starts, capture, assigned inspections). No admin, export or user-search access. Short session, and the offline app stores only assigned data. Immediate revocation by a supervisor or SCIM.
    - **name**: Field PIN / magic-link user
    - **sign in**: Single-use magic link or PIN, hashed at rest, short TTL, device-bound, with POST confirmation so mail scanners cannot consume it. Re-issued per shift or per project.
    - **who**: Field workers, labourers and casual inspectors who contribute diary entries, pre-starts, photos and inspections without a full account.
  -
    - **limits**: Sees only records explicitly shared with them. Can act on client review, hold-point witness, RFI response and issue comments. No internal comments, costs, audit log or other clients' data. Downloads are watermarked and logged.
    - **name**: External portal client
    - **sign in**: Magic link to a separate portal origin with its own session policy. Optional email, password and MFA, or federated SSO for large clients.
    - **who**: Client representatives (e.g. Rio Tinto reviewers and witnesses), consultants and third-party witnesses.
  -
    - **limits**: Team-based visibility: sees only their own team's scopes, inspections, certificates and records. Cannot see other subcontractors' data, rates or internal QA. Their certificates and competencies are subject to the same expiry hard-block.
    - **name**: Subcontractor user
    - **sign in**: Email and password with MFA, or magic link or PIN for crew members. Can federate their own IdP later.
    - **who**: Subcontractor staff and supervisors working on the tenant's projects (e.g. scaffold, coating or insulation subcontractors).
  -
    - **limits**: Least-privilege scopes per integration and per project. Rate-limited, IP-allowlistable, with every call attributed in the audit log. Cannot approve, sign or administer users. Secrets are shown once and auto-expire.
    - **name**: System / API client
    - **sign in**: OAuth 2.0 client credentials with scoped, rotatable secrets or mTLS. No interactive login and no password.
    - **who**: Integrations: SAP PM or Maximo connectors, webhook consumers, NDT instrument export agents, inbound capture agents and BI tools.
  -
    - **limits**: No standing access to tenant business data. Access is time-boxed, ticketed, tenant-approved and fully audited. Cannot alter or delete audit, signing or legal-hold records, which sit under separate permissions.
    - **name**: Super-admin (platform operator)
    - **sign in**: SSO with phishing-resistant MFA (WebAuthn) from a separate operator console, with just-in-time elevation.
    - **who**: A very small number of vendor operations staff who manage tenants, hosting shape, feature flags and support.
- **profile fields**:
  -
    - **field**: id
    - **notes**: Primary key. tenant_id is also carried on every row and enforced by row-level security.
    - **required**: true
    - **type**: uuid
  -
    - **field**: tenant_id
    - **notes**: Tenant boundary, set via SET LOCAL app.tenant_id per transaction.
    - **required**: true
    - **type**: uuid
  -
    - **field**: account_type
    - **notes**: Drives the sign-in policy and session limits.
    - **required**: true
    - **type**: enum(staff_sso, local, field_pin, portal_client, subcontractor, system_client, super_admin)
  -
    - **field**: email
    - **notes**: Optional for PIN-only field users, who have a username or employee number instead.
    - **required**: true
    - **type**: string (unique per tenant)
  -
    - **field**: given_name / family_name
    - **notes**: Display name is derived. SCIM-managed for SSO users, so read-only in the UI.
    - **required**: true
    - **type**: string
  -
    - **field**: employee_number
    - **notes**: Used for payroll or HR matching and for PIN login lookup.
    - **required**: false
    - **type**: string
  -
    - **field**: organisation_id
    - **notes**: Employer organisation (tenant, client, subcontractor or supplier). Links to Contacts & companies.
    - **required**: true
    - **type**: uuid
  -
    - **field**: job_title / discipline
    - **notes**: Disciplines (NDT, coating, scaffold, welding...) are tenant-configurable and feed resource planning.
    - **required**: false
    - **type**: string / enum
  -
    - **field**: status
    - **notes**: Deactivation is a soft delete that preserves history, records and signatures.
    - **required**: true
    - **type**: enum(invited, active, suspended, deactivated)
  -
    - **field**: role_assignments
    - **notes**: Project, team or asset-subtree scoped, with optional per-user permission overrides held in a separate table.
    - **required**: true
    - **type**: list of {role, scope_type, scope_id, valid_from, valid_to}
  -
    - **field**: team_ids
    - **notes**: Team membership limits record visibility, e.g. a subcontractor team.
    - **required**: false
    - **type**: uuid[]
  -
    - **field**: mfa_methods / mfa_enrolled_at
    - **notes**: Mandatory for all but field_pin. Recovery codes are stored hashed.
    - **required**: true
    - **type**: json / timestamp
  -
    - **field**: phone
    - **notes**: Personal data, field-masked outside the user's own record and HR roles.
    - **required**: false
    - **type**: string (E.164)
  -
    - **field**: locale / timezone / date_format
    - **notes**: Defaults to en-AU and the project timezone. Used by the terminology dictionary fallback chain.
    - **required**: true
    - **type**: string
  -
    - **field**: signature_card
    - **notes**: Used by E-signatures and Report engine. Changes are audited and versioned.
    - **required**: false
    - **type**: file ref + hash
  -
    - **field**: competencies
    - **notes**: Reads from the Certificates & competency register, not free text, so the expiry hard-block applies.
    - **required**: false
    - **type**: list of certificate refs
  -
    - **field**: notification_preferences
    - **notes**: Channel (in-app, email, push), digest frequency and quiet hours.
    - **required**: false
    - **type**: json
  -
    - **field**: last_login_at / last_active_at
    - **notes**: Feeds dormant-account review, which is an access-review evidence item.
    - **required**: false
    - **type**: timestamp
  -
    - **field**: external_id / idp_connection_id
    - **notes**: SCIM and WorkOS directory identifiers for SSO users.
    - **required**: false
    - **type**: string
  -
    - **field**: consent_and_privacy
    - **notes**: Supports the Australian Privacy Act, call-recording consent and AI governance.
    - **required**: false
    - **type**: json {privacy_notice_version, voice_recording_consent, ai_opt_in}
  -
    - **field**: sync_version / created_at / updated_at / deleted_at
    - **notes**: Standard table conventions for optimistic concurrency and soft delete.
    - **required**: true
    - **type**: int / timestamp
- **roles**:
  -
    - **description**: Platform operator with time-boxed, audited access for tenant provisioning, hosting shape, feature flags and configuration. No standing access to business records, and cannot change audit or legal-hold data.
    - **name**: Super Admin
  -
    - **description**: Customer administrator (e.g. at Kaefer). Manages users, roles, terminology, templates, workflows, rules, integrations and tenant settings.
    - **name**: Tenant Admin
  -
    - **description**: Runs one or more projects: team assignments, scope approval, schedules, commercial changes, handover and portal sharing.
    - **name**: Project Manager
  -
    - **description**: Owns the quality system: templates, ITPs, hold-point policy, NCR and CAPA approval, certificates, audits and quality dashboards.
    - **name**: QA/QC Manager
  -
    - **description**: Owns safety and HSE: incidents, permits, JSAs, temporary-works approvals and safety KPIs. Advanced HSE is enabled per site.
    - **name**: HSE Officer
  -
    - **description**: Leads crews and does the supervisor review step. Assigns work, approves diary seals, issues consumables and manages team records.
    - **name**: Supervisor
  -
    - **description**: Performs inspections, ITP steps, NDT and CUI records, raises issues and submits for review. Works online or offline.
    - **name**: Inspector
  -
    - **description**: Captures photos, diary entries, pre-starts and defects, and executes assigned tasks, often through PIN or magic link. Narrow scope with no approvals.
    - **name**: Field Worker
  -
    - **description**: Controls the document library, revisions, transmittals, inbound capture and data books. Ensures numbering, status and distribution.
    - **name**: Document Controller
  -
    - **description**: External client user (e.g. Rio Tinto) in the portal. Reviews and signs off shared inspections, witnesses hold points and responds to RFIs and submittals.
    - **name**: Client Reviewer
  -
    - **description**: External contractor team member who sees only their own team's work. Records their own work, certificates and responses.
    - **name**: Subcontractor
  -
    - **description**: Read-only internal or external auditor with time-limited access to records, audit trail and evidence. Cannot create or change anything.
    - **name**: Auditor
  -
    - **description**: Non-human integration role for scoped OAuth clients. Reads and writes only the specific resources the connector is granted.
    - **name**: API Client
