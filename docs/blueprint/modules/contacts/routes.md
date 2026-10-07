# Page specs for `contacts`

#### Directory `/contacts` (Contacts & companies)

Tenant-level directory of organisations and people.

- **layout**: Tabs for Organisations and People. Search bar, tag filters and a DataTable.
- **sections**:
  - Tabs
  - Search and tag filters
  - Organisation or people table
  - Type chips (client, contractor, subcontractor, supplier, consultant, authority)
- **actions**:
  - Create
  - Open
  - Import CSV
  - Export
  - Bulk tag
- **access**: Users with contacts.view. External users see only what organisation-type visibility rules allow.

#### Organisation Detail `/contacts/organisations/:id` (Contacts & companies)

View an organisation with its people, projects and certificates.

- **layout**: Header with tabs: Overview, People, Projects and roles, Credentials, History.
- **sections**:
  - Profile (type, ABN or equivalent)
  - People list
  - Project role assignments
  - Credential and insurance expiry links
  - Change history
- **actions**:
  - Edit
  - Add person
  - Assign project role
  - Deactivate
  - Merge
- **access**: contacts.view to read, contacts.edit to change

#### Person Detail `/contacts/people/:id` (Contacts & companies)

View a person with their organisation, roles and linked user.

- **layout**: Single detail page with side panel.
- **sections**:
  - Contact details
  - Organisation
  - Project roles
  - Linked user account
  - Privacy and retention status
- **actions**:
  - Edit
  - Invite as user
  - Deactivate
  - Request erasure (legal-hold aware)
- **access**: contacts.edit. Invite requires identity.invite. Erasure requires contacts.privacy_admin.

#### Create or Edit Organisation or Person `/contacts/new` (Contacts & companies)

Create and edit directory records.

- **layout**: FormRenderer page with live duplicate warning.
- **sections**:
  - Type and core fields
  - Contact details
  - Tags
  - Duplicate suggestions panel
- **actions**:
  - Save
  - Save and add person
  - Cancel
- **access**: contacts.create

#### CSV Import `/contacts/import` (Contacts & companies)

Import contacts using shared import mapping.

- **layout**: Wizard: upload, map, validate, confirm.
- **sections**:
  - File upload
  - Mapping template
  - Validation report
  - Duplicate matches
- **actions**:
  - Upload
  - Map columns
  - Confirm import
  - Roll back
- **access**: contacts.import

#### Duplicates and Merge `/contacts/duplicates` (Contacts & companies)

Review duplicate candidates and merge.

- **layout**: Queue list on the left with a side-by-side compare panel on the right.
- **sections**:
  - Candidate queue with confidence
  - Side-by-side field compare
  - Reference impact summary
  - Merge history
- **actions**:
  - Choose surviving record
  - Merge
  - Dismiss
  - Undo where supported
- **access**: contacts.merge for admins

#### Directory Settings `/settings/contacts` (Contacts & companies)

Configure organisation types, project role names, match rules, tags and retention.

- **layout**: Settings tabs.
- **sections**:
  - Organisation types
  - Project roles
  - Duplicate match rules and thresholds
  - Tags
  - Retention and erasure rules
- **actions**:
  - Add or rename type
  - Edit thresholds
  - Edit retention rule
- **access**: Tenant admins with contacts.admin
