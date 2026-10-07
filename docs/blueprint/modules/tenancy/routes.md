# Page specs for `tenancy`

#### Tenants `/platform/tenants` (Tenancy, organisations & data residency)

Operator register of all tenants and their deployment shape.

- **layout**: DataTable with detail drawer
- **sections**:
  - Filters (deployment, region, status)
  - Tenant table (slug, pooled/siloed, region, status, users, storage)
- **actions**:
  - Open
  - Edit settings
  - Suspend
  - Start offboarding
  - Grant support access
  - Export list
- **access**: Platform operator only

#### Tenant provisioning wizard `/platform/tenants/new` (Tenancy, organisations & data residency)

Create a tenant with region, pack, terminology and admin invite.

- **layout**: Multi-step wizard with review step
- **sections**:
  - Tenant name and region
  - Deployment type
  - Template pack and terminology set
  - Admin email
  - Sample data toggle
  - Review and confirm
- **actions**:
  - Next and back
  - Provision
  - Save draft
- **access**: Platform operator only

#### Tenant settings `/settings/tenant` (Tenancy, organisations & data residency)

Tenant branding, terminology, modules and retention defaults.

- **layout**: Tabbed settings page
- **sections**:
  - Profile and region (read-only)
  - Branding
  - Terminology set
  - Enabled modules
  - Retention defaults
  - Quotas and usage
  - KMS key and residency
  - Support access history
- **actions**:
  - Save
  - Upload logo
  - Enable or disable module
  - Change terminology set
- **access**: Tenant admin

#### Organisations `/settings/organisations` (Tenancy, organisations & data residency)

List owner, client and subcontractor organisations.

- **layout**: DataTable with filters
- **sections**:
  - Organisations table (type, ABN, projects, users, shared assets, status)
  - Filters
- **actions**:
  - Create
  - Deactivate
  - Export
  - Open
- **access**: Tenant admin; project admins read-only

#### Organisation detail `/settings/organisations/:id` (Tenancy, organisations & data residency)

View one organisation's users, projects and shared assets.

- **layout**: Header with tabs
- **sections**:
  - Profile
  - Users
  - Projects
  - Shared assets
  - Visibility profile
- **actions**:
  - Edit
  - Invite user
  - Assign visibility profile
  - Deactivate
- **access**: Tenant admin

#### Asset sharing and party visibility `/settings/asset-sharing` (Tenancy, organisations & data residency)

Define what each party sees on shared assets (for example Rio Tinto sees status and evidence, not rates).

- **layout**: Rules table with visibility-profile editor and preview
- **sections**:
  - Share rules table (asset subtree, organisation, expiry)
  - Visibility profile editor (field-level)
  - Preview as party
- **actions**:
  - Create share
  - Edit profile
  - Set expiry
  - Revoke
  - Preview as organisation
- **access**: Tenant admin and asset owner role

#### Support access approvals `/settings/support-access` (Tenancy, organisations & data residency)

Approve time-boxed vendor support access.

- **layout**: Request list with approval dialog
- **sections**:
  - Pending requests
  - Active grants with banner status
  - History with audit links
- **actions**:
  - Approve with duration
  - Deny
  - Revoke
  - Export log
- **access**: Tenant admin

#### Offboarding `/settings/offboarding` (Tenancy, organisations & data residency)

Run export, legal-hold check, crypto-shred and certificate issue.

- **layout**: Stepper with checklist
- **sections**:
  - Export package
  - Legal-hold check
  - Crypto-shred schedule
  - Signed deletion certificate
- **actions**:
  - Start
  - Download export
  - Confirm shred
  - Download certificate
- **access**: Tenant admin with platform operator co-approval
