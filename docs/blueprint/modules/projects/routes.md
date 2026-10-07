# Page specs for `projects`

#### Project list `/projects` (Projects, sites & classification)

Portfolio register of projects in the tenant, scoped to what the user may see.

- **layout**: Full-width DataTable with table/card toggle, filter bar and right-side quick-view drawer.
- **sections**:
  - Filters: status, work type, client, region
  - Portfolio table: code, name, client, site, work type, region, status, open holds, open NCRs, updated
  - Card view
  - Empty state
- **actions**:
  - Create project
  - Open
  - Export CSV
  - Change work type with impact preview
  - Apply template settings
  - Archive (only if closeout complete)
- **access**: Users with project.view; the all-projects override needs a tenant-level permission. Portal users are excluded.

#### Project setup wizard `/projects/new` (Projects, sites & classification)

Create a project from a work-type template with its sites, scope and members.

- **layout**: Stepper wizard with a summary rail and a final review step.
- **sections**:
  - Basics: code (unique per tenant), name, client organisation, work type, template
  - Site and region: primary site picker or create, region, timezone, currency
  - Scope: asset scope picker
  - Members and default roles
  - Numbering and enabled modules
  - Review with required-items preview
- **actions**:
  - Next/back
  - Save draft
  - Create project
  - Cancel
- **access**: project.create (tenant admin or project manager role).

#### Project dashboard and detail `/projects/:id` (Projects, sites & classification)

Entry point for one project: status, KPIs and links to its parts.

- **layout**: Header with status and actions, KPI strip, tabbed body, tile grid and linked assets panel.
- **sections**:
  - Header and status
  - Overview: client, site, region, timezone, currency, dates
  - KPI strip and tiles
  - Linked assets panel
  - Members summary
  - Activity and scope-change history
- **actions**:
  - Edit
  - Start closeout
  - Archive or reopen
  - Switch to project
  - Open settings
- **access**: Project members with project.view; wider visibility for tenant admins.

#### Scope baseline and asset scope picker `/projects/:id/scope` (Projects, sites & classification)

Link assets to the project and compare baseline with current scope.

- **layout**: Split view with the hierarchy tree on the left and the selected scope table on the right; baseline vs current diff tab.
- **sections**:
  - Asset tree with checkboxes and subtree selection
  - Scope list with baseline status
  - Baseline vs current diff
  - Scope-change history
- **actions**:
  - Add assets or subtree
  - Remove from scope
  - Mark as baseline
  - Add scope change with reason
  - Export diff
- **access**: project.scope.edit; read access for project members.

#### Classification and required items `/projects/:id/classification` (Projects, sites & classification)

Show how the work type drives required approvals, ITP templates, documents and workflows.

- **layout**: Wizard on top, with a required-items checklist below.
- **sections**:
  - Classifier questions
  - Resulting work type
  - Requirement bundle checklist: approvals, ITPs, documents, workflows
  - Impact preview on change
- **actions**:
  - Run classification wizard
  - Change work type
  - Confirm recalculation
  - Export checklist
- **access**: project.classify (project manager); view for members.

#### Members and participant directory `/projects/:id/people` (Projects, sites & classification)

Manage project-scoped roles and external party roles.

- **layout**: Two tabs, each with a table and a side drawer.
- **sections**:
  - Members table with project role
  - Participant directory with party role: client, principal contractor, subcontractor, third-party inspector
  - Default roles
  - Portal grant status per participant
- **actions**:
  - Add or remove member
  - Change role
  - Add participant
  - Invite to portal
  - Export
- **access**: project.members.manage; members can view the directory.

#### Project settings `/projects/:id/settings` (Projects, sites & classification)

Override tenant defaults for this project.

- **layout**: Left settings nav with form panels and inherited-from-tenant indicators.
- **sections**:
  - Region, timezone, currency, units, calendar
  - Numbering schemes and client prefixes
  - Enabled modules
  - Terminology editor
  - Retention overrides (within legal hold limits)
  - Closeout rules
  - External access auto-expiry
- **actions**:
  - Edit
  - Reset to tenant default
  - Preview numbering
  - Save
- **access**: project.settings.edit (project manager, tenant admin).

#### Closeout checklist `/projects/:id/closeout` (Projects, sites & classification)

Show and clear blockers before archive.

- **layout**: Checklist grouped by source module with blocker counts and a sign-off panel.
- **sections**:
  - Open hold points
  - Open NCRs
  - Expiring or open certificates
  - Required documents
  - Sign-off and archive
- **actions**:
  - Jump to blocker
  - Request waiver where permitted
  - Sign off
  - Archive project
- **access**: project.closeout (project manager); view for members.

#### Work-type classification and route designer `/admin/projects/classification` (Projects, sites & classification)

Tenant admins define work types, routes and requirement bundles.

- **layout**: Master list with a visual route designer and bundle editor.
- **sections**:
  - Work type list
  - Route designer
  - Requirement bundles
  - Project templates by work type
  - Preview
- **actions**:
  - Add or edit work type
  - Edit route
  - Save template
  - Publish
  - Test with sample project
- **access**: Tenant admin.

#### Mobile project switcher `/m/projects` (Projects, sites & classification)

Choose the active project in the field.

- **layout**: Full-screen searchable list with recent projects and an offline-available badge.
- **sections**:
  - Recent
  - All my projects
  - Sync status
- **actions**:
  - Select project
  - Download for offline
- **access**: Any internal user with project membership.
