# Page specs for `item_types`

#### Content types `/admin/content-types` (Content types, item types & attributes)

Define record kinds that generate navigation and registers.

- **layout**: Sortable table with a create drawer.
- **sections**:
  - Table: name, icon, sort order, nav entry, item types count, assets count
  - Filters: nav visible, system or custom
- **actions**:
  - Create
  - Open
  - Edit
  - Reorder
  - Show or hide in navigation
  - Delete if unused
- **access**: Tenant admin (config.manage).

#### Content type detail `/admin/content-types/:id` (Content types, item types & attributes)

Drill into the categories and item types of one content type.

- **layout**: Header and tabs.
- **sections**:
  - Definition
  - Default attribute schema
  - Categories
  - Item types
  - Register preview
- **actions**:
  - Edit
  - Add category
  - Add item type
- **access**: Tenant admin.

#### Item type editor `/admin/item-types/:id` (Content types, item types & attributes)

Edit attribute schema and behaviour of an item type.

- **layout**: Two-pane editor with an attribute list and a live form preview.
- **sections**:
  - Definition: name, content type, category, parent
  - Attribute schema, own and inherited
  - Conditional and calculated attributes
  - Units and tolerances
  - Component settings
  - Auto-create ITP/inspection
  - Status set mapping
  - Assets using this type
  - Terminology
- **actions**:
  - Add or reorder attribute
  - Save draft
  - Publish new version
  - Deprecate
- **access**: Tenant admin; publishing may need approval.

#### Schema versions and migration preview `/admin/item-types/:id/versions` (Content types, item types & attributes)

See history and the impact of schema changes.

- **layout**: Version timeline and a side-by-side diff with impact counts.
- **sections**:
  - Version list
  - Diff
  - Impact on existing assets and completed inspections
  - Conflicts
- **actions**:
  - Preview migration
  - Publish
  - Roll forward
  - Export diff
- **access**: Tenant admin.

#### Item categories `/admin/categories` (Content types, item types & attributes)

Group item types and set applicability (Any/Item/Module).

- **layout**: Table with a create drawer.
- **sections**:
  - Table: name, content type, applicable for, item types, updated
- **actions**:
  - Create
  - Edit
  - Delete unused
- **access**: Tenant admin.

#### Attributes registry `/admin/attributes` (Content types, item types & attributes)

Manage shared, reusable attributes.

- **layout**: Table with a detail drawer and merge suggestions.
- **sections**:
  - Attribute list: label, field type, unit, used in
  - Merge suggestions
  - Usage
- **actions**:
  - Create
  - Edit
  - Merge
  - Retire
- **access**: Tenant admin.

#### Status set editor `/admin/status-sets` (Content types, item types & attributes)

Map local statuses to neutral lifecycle states.

- **layout**: List of sets with a mapping grid.
- **sections**:
  - Status sets
  - Mapping to neutral states
  - Usage
- **actions**:
  - Add status
  - Map
  - Save
- **access**: Tenant admin.

#### Starter packs `/admin/starter-packs` (Content types, item types & attributes)

Import NDT/CUI, welding, insulation and coating packs.

- **layout**: Card gallery with a preview and import dialog.
- **sections**:
  - Available packs
  - Pack contents preview
  - Import history
  - Update available
- **actions**:
  - Preview
  - Import
  - Update
- **access**: Tenant admin.
