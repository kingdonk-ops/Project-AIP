# Page specs for `identity`

#### Sign in `/login` (Users, sign-in & SSO)

Entry point for all user classes, with organisation disambiguation.

- **layout**: Centred card with tenant brand (e.g. Kaefer red); SSO redirect when the domain is claimed.
- **sections**:
  - Email entry
  - SSO redirect
  - Password + MFA
  - Magic link/PIN request
  - Organisation chooser
- **actions**:
  - Continue
  - Sign in with SSO
  - Request magic link
  - Enter MFA code
  - Recover access
- **access**: Public; SSO-managed users cannot use password.

#### Magic link confirm `/auth/link/:token` (Users, sign-in & SSO)

POST confirmation page so mail scanners don't consume tokens.

- **layout**: Minimal card with scope summary.
- **sections**:
  - Scope and project summary
  - Device binding notice
  - PIN entry
- **actions**:
  - Confirm and continue
  - Cancel
- **access**: Holder of an unexpired single-use token.

#### Accept invite `/invite/:token` (Users, sign-in & SSO)

Accept invitation and set up credentials.

- **layout**: Single-column wizard.
- **sections**:
  - Invite summary
  - Set password
  - MFA enrolment
- **actions**:
  - Accept
  - Set password
  - Enrol MFA
- **access**: Invited person.

#### Profile `/profile` (Users, sign-in & SSO)

Manage contact details, competencies, signature, MFA, sessions and notification preferences.

- **layout**: Tabbed detail page.
- **sections**:
  - Profile and contact
  - Competencies and signature image
  - Sign-in methods and MFA
  - Sessions and devices
  - Notification preferences
- **actions**:
  - Edit
  - Capture signature
  - Add MFA method
  - Revoke session
  - Download recovery codes
- **access**: Own profile for any signed-in user.

#### User directory `/settings/users` (Users, sign-in & SSO)

Manage users across classes with MFA and SCIM status.

- **layout**: Register with filter bar and right detail drawer for access scope.
- **sections**:
  - User table
  - Detail drawer (profile, roles and scope, sessions, SCIM linkage, sponsor, audit)
  - Invite blade
- **actions**:
  - Invite
  - Edit
  - Deactivate
  - Revoke sessions
  - Reset MFA
  - Resend invite
  - Export
- **access**: Tenant admin and user-admin permission; project admins limited to their project.

#### SSO and SCIM `/settings/identity/sso-scim` (Users, sign-in & SSO)

Configure SSO enforcement, domain claims and monitor SCIM sync.

- **layout**: Status panels plus settings form; link to WorkOS admin portal.
- **sections**:
  - SSO connection status
  - Domain claims and enforcement
  - SCIM sync status and errors
  - Group-to-role mapping
- **actions**:
  - Open admin portal
  - Enforce SSO
  - Map group
  - Retry sync
- **access**: Tenant admin.

#### MFA and session policy `/settings/identity/policies` (Users, sign-in & SSO)

Set MFA, session lifetime, magic link and password policies per user class.

- **layout**: Settings form grouped by user class.
- **sections**:
  - MFA by role and class
  - Idle and absolute timeouts
  - Token lifetimes
  - Magic link TTL and lockout
  - Password policy
- **actions**:
  - Save
  - Reset to default
- **access**: Tenant admin; security admin.

#### Active sessions `/settings/identity/sessions` (Users, sign-in & SSO)

View and revoke sessions across users.

- **layout**: Register table.
- **sections**:
  - Sessions table (User, Device, IP, Started, Last active)
- **actions**:
  - Revoke
  - Revoke selected
- **access**: Tenant admin and security admin.

#### API keys and clients `/settings/identity/api-keys` (Users, sign-in & SSO)

Manage scoped, expiring API keys and OAuth clients.

- **layout**: Register with create blade showing the secret once.
- **sections**:
  - Keys table
  - Scope picker
  - Per-key audit
- **actions**:
  - Create
  - Rotate
  - Revoke
  - View audit
- **access**: Tenant admin with integrations permission.

#### External accounts `/settings/identity/external` (Users, sign-in & SSO)

Track sponsors, expiry and re-confirmation of external users.

- **layout**: Register with expiry filters.
- **sections**:
  - External accounts table
  - Sponsor and expiry
  - Reconfirmation queue
- **actions**:
  - Reconfirm
  - Extend
  - Expire now
  - Change sponsor
- **access**: Tenant admin and sponsors for their own accounts.

#### Break-glass and login-as `/settings/identity/break-glass` (Users, sign-in & SSO)

Request and approve time-boxed elevation with dual approval.

- **layout**: Request list with approval blade.
- **sections**:
  - Active grants
  - Pending requests
  - Audit trail
- **actions**:
  - Request
  - Approve
  - Deny
  - End early
- **access**: Designated break-glass requesters and approvers.

#### Field PIN sign-in and quick-switch (mobile) `/m/login` (Users, sign-in & SSO)

Fast sign-in on shared devices with auto-lock.

- **layout**: Full-screen numeric keypad with large keys and user tiles.
- **sections**:
  - User tiles
  - PIN pad
  - Lock state
  - Offline sign-in notice
- **actions**:
  - Select user
  - Enter PIN
  - Lock
  - Switch user
- **access**: Field and external users with device binding.
