# Page specs for `design`

#### Home: My Work `/` (Design system & app shell)

Prioritised queue of what the user must act on, with expiring credentials and a week view.

- **layout**: Two columns under the app shell: queue on the left, right column with expiring credentials/calibrations and week calendar. Mobile: single column with a next-action card.
- **sections**:
  - Prioritised My Work queue
  - Inline primary actions (Approve, Open, Sign)
  - Expiring credentials and calibrations panel
  - Week calendar
  - KPI strip (role default)
- **actions**:
  - Approve
  - Open record
  - Sign
  - Filter queue
  - Switch scope
- **access**: All signed-in users; content filtered by the policy layer.

#### Component library / style reference `/settings/design/style-reference` (Design system & app shell)

Living reference for tokens, components and status chips; shows accessibility and visual regression results.

- **layout**: Left section index, main canvas with component examples, light/dark/high-contrast toggle.
- **sections**:
  - Tokens (colour, type, spacing, radii)
  - Status chips with icon and label
  - Dialogs, toasts, empty/loading/error states
  - Offline and sync-conflict variants
  - Accessibility and visual regression results
- **actions**:
  - Switch theme
  - Toggle density
  - Copy token
  - Open results
- **access**: Tenant admins and designers; read-only for staff users.

#### Tenant theme `/settings/design/theme` (Design system & app shell)

Set accent, density and contrast theme with live preview.

- **layout**: Settings form on the left, live preview of shell and register on the right.
- **sections**:
  - Accent colour token
  - Default density
  - High-contrast outdoor theme availability
  - Touch target size
  - Live preview
- **actions**:
  - Change accent
  - Save
  - Reset to default
  - Preview field mode
- **access**: Tenant admin.

#### Saved views `/settings/design/saved-views` (Design system & app shell)

Manage personal, team and project saved views and role defaults.

- **layout**: Standard register with filter bar, bulk actions and a slide-over blade for create/edit.
- **sections**:
  - Views table (Name, Module, Owner, Scope, Role default, Shared with, Last used, URL)
  - Filter builder blade
  - Invalid-filter warnings
- **actions**:
  - Open
  - Rename
  - Duplicate
  - Copy link
  - Share
  - Set role default
  - Delete
  - Bulk share or change scope
- **access**: Own views for all users; team/project sharing needs team or project rights; role defaults for admins.

#### Shell and navigation settings `/settings/design/shell` (Design system & app shell)

Configure nav rail items and order per role or market, home layout per role, and field mode enablement per project.

- **layout**: Settings page with role selector, drag-order list and project table.
- **sections**:
  - Nav rail order per role
  - Default home layout per role
  - Field mode per project
  - Command palette recents retention
  - Export column policy
- **actions**:
  - Reorder
  - Enable field mode
  - Save
  - Reset
- **access**: Tenant admin.

#### My display preferences `/settings/design/preferences` (Design system & app shell)

Per-user density, column and theme preferences.

- **layout**: Single-column form.
- **sections**:
  - Density toggle
  - Contrast theme
  - Column preferences
  - Recent items clear
- **actions**:
  - Save
  - Clear recents
  - Reset columns
- **access**: Any signed-in user, own preferences only.

#### Reference layouts `/settings/design/layouts/:pattern` (Design system & app shell)

Reference screens for register, record detail, split-pane, blade, dashboard, document viewer, ITP execution and field mode that modules assemble.

- **layout**: Pattern gallery with full-screen demos populated with sample data.
- **sections**:
  - Register
  - Record detail with workflow bar and right rail
  - Split-pane tree + detail
  - Blade
  - KPI tile dashboard
  - Three-pane document viewer
  - ITP execution
  - Field mode
- **actions**:
  - Open pattern
  - Toggle office/field mode
  - Toggle density
- **access**: Designers and tenant admins; internal users read-only.

#### Field mode home (mobile) `/m/home` (Design system & app shell)

Simplified shell with large next-action card for field users.

- **layout**: Full-screen mobile, 56px header with sync chip, big next-action card, bottom one-hand navigation, 48px+ touch targets.
- **sections**:
  - Next-action card
  - Today's tasks list
  - Sync status chip
  - Offline and conflict banner
- **actions**:
  - Start next action
  - Open task
  - Resolve sync conflict
  - Switch user (PIN quick-switch)
- **access**: Field users and staff on projects with field mode enabled.
