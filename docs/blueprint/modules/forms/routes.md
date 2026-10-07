# Page specs for `forms`

#### Template register `/templates` (Form & template designer)

List all templates by kind, status and category.

- **layout**: Data table with filters and bulk bar.
- **sections**:
  - Filters (kind, category, status, competency)
  - Table (name, kind, revision, status, usage)
  - Deleted templates toggle
- **actions**:
  - Create
  - Clone
  - Archive
  - Retire
  - Export JSON
  - Import
  - Restore
  - Change category
- **access**: Template admins and quality managers; others read-only

#### Create template `/templates/new` (Form & template designer)

Capture basics before opening the designer.

- **layout**: Short modal/page form.
- **sections**:
  - Name, kind, category
  - Required competency, default frequency
  - Start from blank, clone or starter pack
- **actions**:
  - Create draft
  - Cancel
- **access**: Template admins

#### Template detail `/templates/:id` (Form & template designer)

Overview, revisions and usage.

- **layout**: Header with status and workflow bar; tabs.
- **sections**:
  - Summary and settings
  - Revision history and compare
  - Usage (inspections, programmes, report mappings)
  - Report slot mapping
  - Audit trail
- **actions**:
  - Edit draft
  - Submit for approval
  - Approve/reject
  - Publish revision
  - Retire
  - Delete/restore
  - Export
- **access**: Template admins; approvers; read-only for others

#### Designer `/templates/:id/revisions/:rev/design` (Form & template designer)

Drag-and-drop form building.

- **layout**: Three panes: field palette, canvas, properties; top toolbar with preview toggles.
- **sections**:
  - Field palette (all field types)
  - Canvas with sections and grid/tabular layouts
  - Field properties (type, unit, limits, expiry flag, references)
  - Conditional logic builder (visible_if, required_if)
  - Calculated fields and validation rules
  - Repeating tables with row validation
  - Print layout preview
  - Mobile/offline preview
  - Test console with sample data
  - Lint results
- **actions**:
  - Add/move/delete field
  - Edit logic
  - Run tests
  - Save draft
  - Preview
  - Publish (blocked if tests fail)
- **access**: Template authors; publish requires approver role if approval is enabled

#### Revision compare `/templates/:id/revisions/compare` (Form & template designer)

Diff two revisions.

- **layout**: Side-by-side diff.
- **sections**:
  - Field/section changes
  - Logic and validation changes
  - Impact on in-flight inspections
- **actions**:
  - Select revisions
  - Restore as new draft
- **access**: Template admins and approvers

#### Form settings `/settings/forms` (Form & template designer)

Tenant rules for the designer.

- **layout**: Settings cards.
- **sections**:
  - Approval requirement and roles
  - Allowed field types
  - Expression limits
  - Units by market
  - Option lists
  - Template kind labels
  - Starter packs
- **actions**:
  - Edit
  - Save
  - Manage option lists
- **access**: Tenant admin

#### Starter template library `/templates/library` (Form & template designer)

Browse and import market-pack templates.

- **layout**: Card grid with preview drawer.
- **sections**:
  - Packs (coating ITR, UTT, pre-start, torque, welding, concrete, CUI)
  - Preview
- **actions**:
  - Import as draft
  - Preview
- **access**: Template admins
