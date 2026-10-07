# Page specs for `ref_packs`

#### Library Manager `/settings/reference-packs` (Regional reference data packs)

Enable, import, version and manage reference packs for the tenant.

- **layout**: Card or table list of available and enabled packs with licence badges.
- **sections**:
  - Available shipped packs (for example AU-WA starter pack)
  - Enabled packs with version
  - Customer-loaded licensed libraries with licence flag
  - Pack detail drawer
- **actions**:
  - Enable pack
  - Disable pack
  - Import licensed content
  - Set licence flag
  - View versions
- **access**: Tenant admins with refpacks.admin

#### Pack Detail `/settings/reference-packs/:id` (Regional reference data packs)

Browse a pack's items, standards and versions.

- **layout**: Tabs: Items, Standards map, Versions, Usage.
- **sections**:
  - Item table (code, description, unit)
  - Standards-to-checklist mapping
  - Version history
  - Projects pinned to each version
- **actions**:
  - Search items
  - Map standard clause to checklist item
  - Create version
  - Export
- **access**: refpacks.view to read, refpacks.admin to edit

#### Licensed Content Import `/settings/reference-packs/:id/import` (Regional reference data packs)

Customer loads its own licensed data, which stays tenant-owned and is never shared.

- **layout**: Wizard: licence confirmation, upload, mapping, validate, confirm.
- **sections**:
  - Licence acknowledgement
  - File upload and mapping
  - Validation report
  - Confirmation
- **actions**:
  - Confirm licence
  - Upload
  - Map
  - Confirm import
  - Roll back
- **access**: refpacks.admin

#### Upgrade Preview `/settings/reference-packs/:id/upgrade` (Regional reference data packs)

Show the impact of a new pack version before projects adopt it.

- **layout**: Diff view with an affected-references panel.
- **sections**:
  - Added, changed and removed items
  - Affected records and checklist links
  - Projects pinned to the old version
- **actions**:
  - Approve upgrade for a project
  - Keep pinned
  - Export diff
- **access**: refpacks.admin or project admins for their own project

#### Project Pack Pins `/projects/:projectId/settings/reference-packs` (Regional reference data packs)

Pin pack versions per project.

- **layout**: Table of packs with pinned version and an upgrade indicator.
- **sections**:
  - Pinned versions
  - Upgrade available badges
- **actions**:
  - Pin version
  - Open upgrade preview
- **access**: Project admins

#### Currency and Rate Settings `/settings/currencies` (Regional reference data packs)

Manage currencies, tax rates and exchange rate sources.

- **layout**: Two tables with a source configuration panel.
- **sections**:
  - Currencies
  - Tax rates
  - Exchange rates with source and effective date
- **actions**:
  - Add currency
  - Set rate
  - Choose source
  - Edit tax rate
- **access**: Tenant admins with refpacks.admin

#### Market and Jurisdiction Bundles `/settings/markets` (Regional reference data packs)

Enable a market in one step: terminology, tax, holidays and formats.

- **layout**: Bundle cards with a preview of what will change.
- **sections**:
  - Available bundles (AU-WA first)
  - Preview of terminology, holidays and formats
  - Currently applied bundle
- **actions**:
  - Apply bundle
  - Preview changes
  - Override a setting
- **access**: Tenant admins

#### Reference Picker (shared component) `component:reference-picker` (Regional reference data packs)

Reusable picker used inside other modules to select a reference item, standard clause or currency.

- **layout**: Searchable popover or dialog with pinned-version indicator.
- **sections**:
  - Search
  - Result list with code and description
  - Version badge
- **actions**:
  - Search
  - Select
  - Clear
- **access**: Any user with access to the host module
