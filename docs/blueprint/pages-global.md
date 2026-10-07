# Global pages (auth, shell, profile, errors)

#### Sign in `/login` (global)

Entry for staff and customers; email first, then route to SSO or password by domain.

- **layout**: Centred card on auth shell, tenant-branded accent
- **sections**:
  - Email field
  - Password step
  - SSO redirect notice
  - Magic link/PIN option
  - Footer links: terms, privacy
- **actions**:
  - Continue
  - Sign in with SSO
  - Send magic link
  - Forgot password
- **access**: Public. Generic error messages and rate limiting to avoid account enumeration.

#### Create account `/register` (global)

Self sign-up only where the tenant or market model allows it; otherwise invite-only.

- **layout**: Centred card on auth shell
- **sections**:
  - Name, work email, password with strength meter
  - Terms and privacy acceptance
  - MFA enrolment next step
- **actions**:
  - Create account
  - Back to sign in
- **access**: Public, feature-flagged per tenant. Hidden or shows 'invite only' when disabled.

#### Forgot password `/forgot-password` (global)

Request a reset link.

- **layout**: Centred card
- **sections**:
  - Email field
  - Neutral confirmation message
- **actions**:
  - Send reset link
  - Back to sign in
- **access**: Public. SSO-managed users are told to use their identity provider.

#### Reset password `/reset-password/:token` (global)

Set a new password via single-use, short-TTL token.

- **layout**: Centred card
- **sections**:
  - New password and confirm
  - Policy checklist
  - Expired or used token state
- **actions**:
  - Set password
  - Request new link
- **access**: Public with valid token. Revokes existing sessions on success.

#### MFA challenge `/mfa/verify` (global)

Second factor at sign-in.

- **layout**: Centred card
- **sections**:
  - TOTP or WebAuthn prompt
  - Recovery code option
  - Trust-device notice
- **actions**:
  - Verify
  - Use recovery code
  - Cancel
- **access**: Partially authenticated session.

#### MFA enrolment `/mfa/enrol` (global)

Mandatory first-time setup where MFA is enforced.

- **layout**: Stepper in auth shell
- **sections**:
  - Choose method (authenticator app, passkey/security key)
  - QR code and confirm code
  - Recovery codes download
- **actions**:
  - Confirm
  - Download codes
  - Skip (blocked when enforced)
- **access**: Partially authenticated users required to enrol.

#### Accept invite `/invite/:token` (global)

New user joins a tenant, organisation or project.

- **layout**: Centred card
- **sections**:
  - Inviter, organisation and role summary
  - Set name and password, or continue with SSO
  - MFA enrolment handoff
- **actions**:
  - Accept invite
  - Decline
  - Request new invite
- **access**: Valid invite token only. Expired and revoked states shown.

#### Magic-link / PIN landing `/link/:token` (global)

Scoped entry for field and external users, with POST confirmation so mail scanners cannot consume the link.

- **layout**: Minimal large-touch card
- **sections**:
  - Named project and module scope
  - Confirm button
  - PIN entry fallback
  - Expired, used or wrong-device states
- **actions**:
  - Continue
  - Enter PIN
  - Request new link
- **access**: Single-use, short TTL, device-bound. Lands in the portal or field shell.

#### SSO callback and errors `/sso/callback` (global)

Complete SAML/OIDC sign-in and explain failures.

- **layout**: Auth shell status page
- **sections**:
  - Progress state
  - Error detail (unassigned user, deprovisioned, domain mismatch)
  - Contact admin
- **actions**:
  - Retry
  - Back to sign in
- **access**: Public, transient.

#### Home / My Work `/` (global)

One queue of everything the person needs to do, with overdue escalation.

- **layout**: App shell, KPI strip above split list
- **sections**:
  - KPI strip (due today, overdue, awaiting my sign-off)
  - My Work queue (tasks, inspections to review, approvals, RFIs, actions)
  - Expiring certificates and calibrations I own
  - Recent activity on my assets
  - Saved views
- **actions**:
  - Open item
  - Complete or reassign task
  - Filter by scope
  - Save view
  - Create task
- **access**: All signed-in internal users; content filtered by permissions and scope bar.

#### Notifications `/notifications` (global)

Inbox of mentions, assignments, approvals, deadlines and alerts.

- **layout**: Register pattern with detail drawer
- **sections**:
  - Tabs: All, Unread, Mentions, Approvals, Deadlines
  - Grouped by day
  - Link to source record
- **actions**:
  - Mark read/unread
  - Mark all read
  - Snooze
  - Open source
  - Notification preferences
- **access**: Own notifications only.

#### Global search results `/search` (global)

Permission-filtered search across assets, inspections, issues, documents, reports and correspondence.

- **layout**: Filter rail plus result list with preview pane
- **sections**:
  - Query bar with scope chips
  - Type tabs with counts
  - Filters (asset subtree, NDT method, date, status, project)
  - Results with highlighted match and asset breadcrumb
  - Saved searches
- **actions**:
  - Refine filters
  - Save as view or tile
  - Open result
  - Export results
- **access**: Results limited by the caller's permissions and scope.

#### Profile `/profile` (global)

Personal details, security and preferences.

- **layout**: Record-detail with tabs
- **sections**:
  - Details and signature card
  - Competencies and certificates (read-only link)
  - Security (password, MFA methods, passkeys, sessions)
  - Preferences (language, timezone, date format, theme density)
  - Notification preferences
  - API tokens (where permitted)
- **actions**:
  - Edit details
  - Change password
  - Add or remove MFA method
  - Revoke session
  - Sign out everywhere
- **access**: Own profile. Fields managed by SCIM are read-only.

#### Settings overview `/settings` (global)

Landing for admin with setup checklist and health.

- **layout**: Card grid with left sub-nav
- **sections**:
  - Setup progress
  - Security posture (MFA coverage, SSO status)
  - Recent admin changes
- **actions**:
  - Jump to setting area
- **access**: Any admin-type permission; cards limited to areas the user can manage.

#### Organisation `/settings/organisation` (global)

Tenant and client organisation details, regional defaults, branding.

- **layout**: Record-detail with tabs
- **sections**:
  - Tenant profile
  - Client organisations (for example Rio Tinto within Kaefer)
  - Regional settings (timezone, currency, units, date format)
  - Branding (logo, accent colour)
  - Data residency and hosting information
  - Enabled modules and site feature flags (for example HSE advanced pack)
- **actions**:
  - Edit
  - Add client organisation
  - Toggle modules
  - Upload logo
- **access**: Tenant admin.

#### Users `/settings/users` (global)

Manage accounts, invitations and status.

- **layout**: Register with record-detail drawer
- **sections**:
  - User table (name, org, roles, team, status, MFA, last active, source: SCIM/local)
  - Pending invites
  - Detail: roles by project, overrides, sessions, audit
- **actions**:
  - Invite user
  - Bulk import CSV
  - Deactivate
  - Resend invite
  - Reset MFA
  - Revoke sessions
  - Export
- **access**: User admin. SCIM-managed fields locked.

#### Roles & permissions `/settings/roles` (global)

Define roles from the single permissions catalogue.

- **layout**: Master-detail with permission matrix
- **sections**:
  - Role list (system and custom)
  - Permission matrix by module and action
  - Scope rules (project, team, asset subtree)
  - Users in role
  - Effective-access simulator
- **actions**:
  - Create or clone role
  - Edit permissions
  - Test as user
  - Delete (if unused)
- **access**: Access admin. System roles are read-only.

#### Teams `/settings/teams` (global)

Teams that limit record visibility, for example subcontractor teams.

- **layout**: Register with detail
- **sections**:
  - Team list
  - Members
  - Visibility rules and asset subtree scope
  - Linked projects
- **actions**:
  - Create team
  - Add or remove members
  - Set visibility
  - Archive
- **access**: Access admin or project admin.

#### SSO & SCIM `/settings/sso` (global)

Configure SAML 2.0 and directory provisioning.

- **layout**: Stepper plus status panels
- **sections**:
  - Connection setup (metadata, certificates, domain)
  - Attribute and group-to-role mapping
  - SCIM endpoint and token
  - Provisioning log and errors
  - Enforcement policy (SSO required, MFA enforcement, session length)
  - Test sign-in
- **actions**:
  - Create connection
  - Test
  - Rotate SCIM token
  - Enforce SSO
  - Disable
- **access**: Tenant admin and security admin.

#### Terminology `/settings/terminology` (global)

Rename terms per market, client and language without changing behaviour.

- **layout**: Editable register with live preview
- **sections**:
  - Key table (key, platform default, tenant override, client override)
  - Search and module filter
  - Preview in context
  - Language packs and market presets
  - Missing or untranslated keys
- **actions**:
  - Edit override
  - Import or export CSV
  - Apply preset
  - Reset to default
  - Publish changes
- **access**: Tenant admin. Internal status codes are never editable.

#### Content types `/settings/content-types` (global)

Define kinds of records that get nav entries and generated registers.

- **layout**: Register with record-detail
- **sections**:
  - Content type list (Asset, Staff, Vehicles, Equipment, Consumables, RSW, custom)
  - Nav placement and icon
  - Register column and default view config
  - Linked workflows and templates
- **actions**:
  - Create
  - Rename
  - Reorder in nav
  - Enable or disable
  - Archive
- **access**: Configuration admin.

#### Item types & attributes `/settings/item-types` (global)

Categories, item types and attribute schemas.

- **layout**: Tree on left, schema editor on right
- **sections**:
  - Category and type tree
  - Attribute list (type, required, unit, expiry flag, reference fields)
  - Validation rules
  - Preview form
  - Usage count
- **actions**:
  - Add category, type or attribute
  - Reorder
  - Set expiry-flag field
  - Merge or deprecate
  - Import schema
- **access**: Configuration admin. Changes versioned.

#### Workflows & rules `/settings/workflows` (global)

Edit state machines, approval routes and guard rules per record type.

- **layout**: Diagram canvas with side panel
- **sections**:
  - Workflow list by record type
  - States and transitions with role and guard
  - Approval routes and delegation
  - Rules and validation (block or warn)
  - Rule test panel
  - Version history
- **actions**:
  - Create or clone workflow
  - Edit transition
  - Add guard rule
  - Test with sample record
  - Publish version
- **access**: Configuration admin. Published versions apply to new records.

#### Templates `/settings/templates` (global)

Admin index of form, ITP, report and notification templates; opens the form designer owned by its module.

- **layout**: Register
- **sections**:
  - Template list (kind, revision, status, usage)
  - Report templates
  - Revision history
- **actions**:
  - New template
  - Open designer
  - Publish or retire
  - Duplicate
  - Import or export
- **access**: Template admin.

#### Notification settings `/settings/notifications` (global)

Tenant-wide notification rules and defaults.

- **layout**: Tabs
- **sections**:
  - Events and channels matrix (in-app, email, chat)
  - Escalation and grace periods
  - Expiry reminder lead times (suppressed for unavailable or out-of-stock items)
  - Email and message templates with terminology keys
  - Quiet hours
- **actions**:
  - Edit rule
  - Send test
  - Reset to default
- **access**: Tenant admin.

#### Integrations `/settings/integrations` (global)

Connectors, API access and webhooks.

- **layout**: Card grid plus detail
- **sections**:
  - Connectors (SAP PM, Maximo, Teams, Slack, calendar/iCal)
  - API clients (OAuth client credentials) and scopes
  - Webhooks with delivery log and retries
  - Inbound capture channels (off by default)
- **actions**:
  - Connect or disconnect
  - Create API client
  - Rotate secret
  - Add webhook
  - Replay delivery
- **access**: Integration admin.

#### Retention & legal hold `/settings/retention` (global)

Retention policies and holds on records.

- **layout**: Tabs
- **sections**:
  - Retention policies by record type
  - Legal holds (scope, reason, custodians, status)
  - Held records list
  - Deletion and disposal queue
  - Recycle bin
- **actions**:
  - Create policy
  - Place or release hold (dual approval)
  - Restore record
  - Approve disposal
- **access**: Records manager or compliance admin. Hold actions fully audited.

#### Audit log `/settings/audit-log` (global)

Tamper-evident log of all significant events.

- **layout**: Register with filters and detail drawer
- **sections**:
  - Filters (actor, action, record, asset, date, IP)
  - Event table with before and after
  - Hash-chain integrity status and anchor info
- **actions**:
  - Filter
  - Export
  - Verify chain
  - Save view
- **access**: Auditor permission, separate from app admin. Read-only.

#### Billing & usage `/settings/billing` (global)

Plan, seats and usage for hosted tenants.

- **layout**: Summary cards plus table
- **sections**:
  - Plan and seats
  - Usage (storage, SSO or SCIM connections)
  - Invoices
  - Billing contacts
- **actions**:
  - Change plan
  - Download invoice
  - Update contacts
- **access**: Billing admin. Hidden on siloed or contract-billed tenants.

#### Security policies `/settings/security` (global)

Tenant security controls.

- **layout**: Form sections
- **sections**:
  - MFA enforcement
  - Password policy
  - Session timeouts
  - Magic link and PIN policy (TTL, scope)
  - IP allow-list
  - Active sessions overview
- **actions**:
  - Save policy
  - Revoke all sessions
- **access**: Security admin.

#### Import, export & backup `/settings/data` (global)

Bulk data movement and tenant export.

- **layout**: Tabs with job list
- **sections**:
  - Import wizard with dry-run report
  - Export registers
  - Full tenant export
  - Job history
- **actions**:
  - Start import
  - Download dry-run
  - Commit
  - Request tenant export
- **access**: Data admin.

#### AI controls `/settings/ai` (global)

Enable AI features and view the data-flow register.

- **layout**: Form plus register
- **sections**:
  - Feature toggles (opt-in per tenant)
  - Provider and region register
  - Usage log
- **actions**:
  - Enable or disable feature
  - View register entry
- **access**: Tenant admin and security admin. Hidden until AI features ship.

#### Background jobs `/settings/jobs` (global)

Visible state of imports, exports, report renders and syncs.

- **layout**: Register
- **sections**:
  - Job table (type, status, started, duration, error)
  - Detail with log
- **actions**:
  - Retry
  - Cancel
  - Download output
- **access**: Admin.

#### Access denied `/403` (global)

Explain missing permission without leaking record existence.

- **layout**: Centred status page inside shell
- **sections**:
  - Message
  - Required permission hint
  - Request access
- **actions**:
  - Request access
  - Go home
  - Switch scope
- **access**: Any signed-in user.

#### Not found `/404` (global)

Missing or unavailable page or record.

- **layout**: Centred status page
- **sections**:
  - Message
  - Search box
  - Recent items
- **actions**:
  - Search
  - Go home
  - Back
- **access**: Public and signed-in variants.

#### Server error `/500` (global)

Unexpected failure with a reference ID.

- **layout**: Centred status page
- **sections**:
  - Plain message
  - Reference ID
  - Status link
- **actions**:
  - Retry
  - Copy reference
  - Report problem
- **access**: Any. Details are scrubbed.

#### Offline `/offline` (global)

Show what works without signal.

- **layout**: Banner plus fallback page
- **sections**:
  - Connection state
  - Available offline items (downloaded assets, drafts)
  - Queued changes count
- **actions**:
  - Continue offline
  - Retry connection
  - Open sync queue
- **access**: Any, via service worker.

#### Maintenance & session expired `/maintenance` (global)

Planned downtime and session timeout handling.

- **layout**: Centred status page
- **sections**:
  - Message and expected return
  - Session expired variant with sign-in
- **actions**:
  - Sign in again
  - Check status
- **access**: Public.

#### Mobile shell: Today `/m` (global)

Field home with assigned work for today.

- **layout**: Bottom tabs, large touch targets, offline banner
- **sections**:
  - Today's assigned inspections and tasks
  - Hold points due
  - Expiry alerts for my instruments
  - Sync status chip
- **actions**:
  - Open item
  - Scan QR/NFC
  - Switch project
- **access**: Field and internal users with the mobile permission.

#### Mobile shell: Capture `/m/capture` (global)

Fast capture of photo, voice, form or defect.

- **layout**: Full-screen action sheet with large Capture button
- **sections**:
  - Capture options
  - Asset context (last used or scanned)
  - Draft queue
- **actions**:
  - Take photo
  - Record voice note
  - Start form
  - Raise defect
- **access**: Field and internal users.

#### Mobile shell: Inspections `/m/inspections` (global)

Downloaded and assigned inspections.

- **layout**: List with status filters
- **sections**:
  - Assigned
  - In progress
  - Awaiting sync
- **actions**:
  - Open
  - Start
  - Download for offline
- **access**: Per inspection permissions.

#### Mobile shell: Sync `/m/sync` (global)

Control and transparency for offline sync.

- **layout**: Status list
- **sections**:
  - Last sync and storage used
  - Outbox with per-item state
  - Conflicts needing merge
  - Sync scope (sites, projects)
- **actions**:
  - Sync now
  - Resolve conflict
  - Retry failed
  - Clear synced media
  - Change scope
- **access**: Any mobile user.

#### External portal shell `/portal` (global)

Narrow shell for clients and subcontractors on a separate origin.

- **layout**: Reduced header, no admin nav, scoped asset tree
- **sections**:
  - Shared records
  - Awaiting my sign-off
  - Documents shared with me
- **actions**:
  - Open shared item
  - Sign off
  - Comment
- **access**: Magic-link users within explicit share scope, separate session policy.
