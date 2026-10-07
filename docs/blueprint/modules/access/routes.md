# Page specs for `access`

#### Roles `/settings/access/roles` (Roles, permissions & teams)

Create and manage roles from the permission catalogue.

- **layout**: Register with role editor blade and catalogue multi-select grouped by module.
- **sections**:
  - Roles table
  - Permission picker
  - Users with role
- **actions**:
  - Create
  - Edit
  - Duplicate
  - Delete
  - View users
  - Export matrix
  - Submit for approval
- **access**: Tenant admin with role-management permission.

#### Permission matrix `/settings/access/matrix` (Roles, permissions & teams)

Per-project matrix of roles against catalogue abilities.

- **layout**: Wide matrix grid with project selector and sticky headers.
- **sections**:
  - Matrix grid
  - Project selector
  - Diff vs default
- **actions**:
  - Export
  - Compare projects
  - Open role
- **access**: Tenant admin, project admin and auditors (read).

#### Role assignments `/settings/access/assignments` (Roles, permissions & teams)

Assign roles with project, team or asset-subtree scope and end dates.

- **layout**: Register with assignment blade and tree picker.
- **sections**:
  - Assignments table
  - Asset subtree picker with exclusions
  - Per-user overrides
- **actions**:
  - Assign
  - Edit
  - Remove
  - Explain access
  - Bulk assign
- **access**: Project admin for own projects; tenant admin.

#### Teams `/settings/access/teams` (Roles, permissions & teams)

Manage teams, members and visibility rules.

- **layout**: Split pane: team list left, members and rules right.
- **sections**:
  - Team list
  - Members
  - Visibility rules (modules, subtrees, exclusions)
  - Field masks
- **actions**:
  - Create team
  - Add members
  - Remove
  - Edit rules
  - Link SCIM group
  - Delete
- **access**: Tenant admin and project admin.

#### Visibility rule builder `/settings/access/teams/:id/rules` (Roles, permissions & teams)

Build team visibility rules with a preview of what the team sees.

- **layout**: Builder on the left, live preview on the right.
- **sections**:
  - Module/entity picker
  - Asset subtree tree picker with exclusions
  - Field mask templates
  - Preview as team
- **actions**:
  - Add rule
  - Apply mask
  - Preview
  - Save
  - Submit for approval
- **access**: Tenant admin and project admin.

#### Effective-access explorer `/settings/access/explorer` (Roles, permissions & teams)

Explain why a user can or cannot act on a record.

- **layout**: Query form on top, result trace below.
- **sections**:
  - User and record picker
  - Decision with reasons (role, team, subtree, discipline)
  - Masks applied
- **actions**:
  - Explain
  - Open role or rule
  - Export
- **access**: Tenant admin, project admin and auditors.

#### Delegations `/settings/access/delegations` (Roles, permissions & teams)

Time-boxed acting-in-role.

- **layout**: Register with create blade.
- **sections**:
  - Delegations table
  - Active and upcoming
- **actions**:
  - Create
  - End early
  - Approve
- **access**: Users for their own delegation; admins to view all.

#### Discipline and method grants `/settings/access/discipline-grants` (Roles, permissions & teams)

Grant sign-off by discipline and method linked to competency.

- **layout**: Register with competency status.
- **sections**:
  - Grants table
  - Linked certificates
  - Expiry
- **actions**:
  - Grant
  - Revoke
  - Open certificate
- **access**: Quality or competency admin.

#### Access reviews and approvals `/settings/access/reviews` (Roles, permissions & teams)

Run periodic access reviews and approve custom role or override changes.

- **layout**: Review queue with attest controls and export.
- **sections**:
  - Review campaigns
  - Pending approvals
  - Privilege change history
- **actions**:
  - Attest
  - Revoke
  - Approve
  - Reject
  - Export
- **access**: Designated approver and auditors.
