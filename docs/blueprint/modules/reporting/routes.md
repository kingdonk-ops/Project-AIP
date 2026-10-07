# Page specs for `reporting`

#### Project Dashboard `/projects/:pid/dashboard` (Dashboards & KPI reporting)

KPI strip, tile grid and asset heatmap

- **layout**: KPI strip top, configurable tile grid, heatmap panel
- **sections**:
  - KPI strip
  - Tile grid (saved view tiles)
  - Asset heatmap
  - Restricted placeholders
- **actions**:
  - Edit layout
  - Drill into register
  - Add tile
  - Switch dashboard
- **access**: Project members; tiles show 'restricted' without access

#### Portfolio Dashboard `/portfolio` (Dashboards & KPI reporting)

Cross-project roll-up

- **layout**: Same grid with project comparison table
- **sections**:
  - Portfolio KPIs
  - Project table
  - Tiles
- **actions**:
  - Filter projects
  - Drill down
- **access**: Portfolio roles

#### Dashboard Editor `/dashboards/:id/edit` (Dashboards & KPI reporting)

Drag/resize canvas and tile configuration

- **layout**: Canvas with tile library sidebar
- **sections**:
  - Tile library
  - Canvas
  - Tile settings
- **actions**:
  - Add/resize tile
  - Bind saved view
  - Save/share
- **access**: Owner; shared edit with dashboards.manage

#### Trend Views `/projects/:pid/reports/trends` (Dashboards & KPI reporting)

Snapshot trends and period comparison

- **layout**: Chart grid with period selector
- **sections**:
  - Metric selector
  - Charts
  - Comparison
- **actions**:
  - Change period
  - Export
- **access**: reporting.view

#### CUI/NDT Analytics `/projects/:pid/reports/cui-ndt` (Dashboards & KPI reporting)

Finding analytics by asset, system, severity and area

- **layout**: Filter bar, charts, drill-down table
- **sections**:
  - Filters
  - Charts
  - Findings table
- **actions**:
  - Filter
  - Drill to inspection
  - Export
- **access**: reporting.view with inspection scope

#### Handover Readiness by Subtree `/projects/:pid/reports/readiness` (Dashboards & KPI reporting)

Readiness score by asset subtree

- **layout**: Tree with score bars and component breakdown
- **sections**:
  - Tree with scores
  - Score breakdown
  - Weights note
- **actions**:
  - Expand
  - Open handover item
- **access**: reporting.view

#### Template Library `/reports/templates` (Dashboards & KPI reporting)

Browse report templates

- **layout**: Card/list grid
- **sections**:
  - Templates
  - Categories
- **actions**:
  - Open builder
  - Generate
- **access**: reporting.view; manage with reporting.manage

#### Report Builder `/reports/templates/:id/build` (Dashboards & KPI reporting)

Set parameters, preview, generate and schedule

- **layout**: Parameters left, preview right
- **sections**:
  - Parameters
  - Preview
  - Schedule and recipients
- **actions**:
  - Generate
  - Schedule
  - Sign off
  - Export PDF/Excel
- **access**: reporting.generate

#### Run History and Distribution `/reports/runs` (Dashboards & KPI reporting)

Immutable outputs with hash and distribution log

- **layout**: Table with detail drawer
- **sections**:
  - Runs
  - Hash and file
  - Recipients
- **actions**:
  - Download
  - Verify hash
  - Resend
- **access**: reporting.view

#### Alerts and Subscriptions `/settings/reporting/alerts` (Dashboards & KPI reporting)

Threshold alerts and digests

- **layout**: Rule list with editor
- **sections**:
  - Rules
  - Subscriptions
- **actions**:
  - Create rule
  - Subscribe
- **access**: Own subscriptions; rules need reporting.manage

#### Mobile Dashboard `/m/dashboard` (Dashboards & KPI reporting)

Condensed KPIs

- **layout**: Stacked KPI cards
- **sections**:
  - KPI cards
  - Top tiles
- **actions**:
  - Drill down
- **access**: Project members
