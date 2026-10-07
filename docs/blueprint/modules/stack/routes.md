# Page specs for `stack`

#### Architecture decision records `/admin/platform/adrs` (Tech stack)

Index of ADRs including the continue-AIP decision and AGPL clean-room record.

- **layout**: DataTable with detail page
- **sections**:
  - Filter bar (status, date, topic)
  - ADR table
  - Supersession links
- **actions**:
  - Create ADR
  - View
  - Edit
  - Supersede
  - Link to risk
  - Export PDF pack
- **access**: Engineering lead and platform admin edit; security and auditors read-only

#### ADR detail `/admin/platform/adrs/:adrNo` (Tech stack)

Read one decision with context, decision, consequences and revisit trigger.

- **layout**: Document-style single column with metadata sidebar
- **sections**:
  - Context, decision, consequences
  - Revisit trigger
  - Supersedes and superseded-by
  - Linked risks
- **actions**:
  - Edit
  - Supersede
  - Link risk
- **access**: Engineering lead and platform admin edit; others read-only

#### Capability and library register `/admin/platform/capabilities` (Tech stack)

One chosen library per capability with licence and adapter status.

- **layout**: DataTable with detail drawer and conformance tab
- **sections**:
  - Capability table (chosen library, alternatives, licence, adapter, status, owner)
  - Storage and queue conformance results
  - Open questions list
- **actions**:
  - Add capability
  - Edit
  - Export to SBOM notes
  - Select adapter per environment
- **access**: Engineering lead and platform admin

#### Licence policy and exceptions `/admin/platform/licences` (Tech stack)

Manage allow and deny lists, SBOM results and time-boxed exceptions.

- **layout**: Tabs: Policy, SBOM, Exceptions
- **sections**:
  - Allow and deny list
  - Latest SBOM violations
  - Exception requests with expiry
  - Provenance log link
- **actions**:
  - Edit lists
  - Request exception
  - Approve or reject exception
  - Download CycloneDX SBOM
- **access**: Exception approver role; engineering read-only

#### Platform version and generated client `/admin/platform/version` (Tech stack)

Show build, commit, runtime and dependency versions and client drift status.

- **layout**: Status cards plus dependency table
- **sections**:
  - Build and commit
  - Runtime versions
  - Generated client status
  - Link to /openapi.json
- **actions**:
  - Copy build info
  - Download SBOM
  - Open OpenAPI schema
- **access**: Platform admin and developers
