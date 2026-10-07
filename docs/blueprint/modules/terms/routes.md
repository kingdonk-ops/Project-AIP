# Page specs for `terms`

#### Dictionary keys `/settings/terms/dictionary` (Terminology dictionary & localisation)

Search keys, preview and override labels across the fallback chain.

- **layout**: Register with filter bar, split-pane preview showing surface (UI/email/PDF/export), blade for override.
- **sections**:
  - Keys table (Key, Default, Effective, Level, Locale, Used in, Last changed)
  - Override blade
  - Where-used panel
  - Override history
- **actions**:
  - Override
  - Preview
  - View where used
  - Reset
  - History
  - Export selected
  - Import overrides
- **access**: Tenant admin and terminology admin; project level overrides for project admins.

#### Terminology packs `/settings/terms/packs` (Terminology dictionary & localisation)

Import, diff, dry-run, apply and roll back packs.

- **layout**: Register of packs; import wizard blade with diff view.
- **sections**:
  - Packs table (Pack, Market, Version, Status, Keys changed, Imported by, Date)
  - Import wizard
  - Diff and dry-run preview
  - Version history
- **actions**:
  - Import pack
  - Dry-run
  - Apply
  - Roll back
  - Export pack
  - Approve (if required)
- **access**: Tenant admin; platform admin for built-in market packs.

#### Untranslated and hard-coded string report `/settings/terms/coverage` (Terminology dictionary & localisation)

Show keys missing in a locale and hard-coded strings found by the linter.

- **layout**: Report table with source filters and detail blade.
- **sections**:
  - Findings table
  - Surface filter (UI/email/PDF/export)
  - Trend since last release
- **actions**:
  - Open source location
  - Create key
  - Mark accepted
  - Export
- **access**: Tenant admin and platform engineers.

#### Glossary and aliases `/settings/terms/glossary` (Terminology dictionary & localisation)

Manage definitions, abbreviations and alias mappings for search and import.

- **layout**: Two tabs, each a register with blade editing.
- **sections**:
  - Glossary entries (term, abbreviation, definition)
  - Aliases (alias to neutral term or field)
  - Tooltip preview
- **actions**:
  - Add
  - Edit
  - Delete
  - Import
  - Export
- **access**: Tenant admin and terminology admin; read for all users via tooltips.

#### Locale, formats and units `/settings/terms/locale` (Terminology dictionary & localisation)

Set locale, date/number formats and display units at tenant and project level.

- **layout**: Settings form with tenant defaults and a project overrides table.
- **sections**:
  - Default locale and fallback chain
  - Date and number formats
  - Display units (mm/in, bar/psi, C/F)
  - Project overrides
  - Sample preview
- **actions**:
  - Save
  - Add project override
  - Reset
- **access**: Tenant admin; project admin for own project.
