# Page specs for `markup`

#### Viewer file list `/viewer` (Markup, viewer & plan room)

Browse drawings and photos with markup state.

- **layout**: Left pane file list with filters, ready to open a canvas in the centre.
- **sections**:
  - Filters (project, asset, type, open markups, revision)
  - File table (file, type, revision, asset, open markups, last markup)
- **actions**:
  - Open
  - Open together
  - Compare revisions
  - Export flattened copy
- **access**: markup.view; files limited by document scope

#### Markup viewer `/viewer/:versionId` (Markup, viewer & plan room)

View and annotate a PDF or photo.

- **layout**: Three panes: file list, canvas with top toolbar, side panel with tabs for comments, versions and approval.
- **sections**:
  - Canvas and toolbar (cloud, arrow, text, dimension, freehand, stamp)
  - Markup threads panel
  - Versions
  - Approval
  - Layers
  - Scale calibration
  - Linked asset and records
  - Export history
- **actions**:
  - Draw markup
  - Reply
  - Resolve or reopen
  - Delete own markup
  - Calibrate scale
  - Apply stamp
  - Link asset
  - Request approval
  - Flatten on approval
- **access**: markup.view to read; markup.create to annotate; stamps and flatten need markup.approve

#### Photo markup `/viewer/photo/:mediaId` (Markup, viewer & plan room)

Mark up site photos with arrows, pins and text, with before and after pairing.

- **layout**: Full-screen canvas with minimal toolbar and a side drawer.
- **sections**:
  - Canvas
  - Pins and notes
  - Before and after pairing
  - Linked inspection or asset
- **actions**:
  - Add pin
  - Add arrow or text
  - Pair before and after
  - Save
  - Export flattened
- **access**: markup.create; GPS stripped by default

#### Plan room `/assets/plan-room` (Markup, viewer & plan room)

Full-screen drawing with defect, photo, inspection and note pins.

- **layout**: Full-screen canvas, layer panel on the left, pin detail popover and record side drawer.
- **sections**:
  - Layer toggles (pins, markups, photos)
  - Area filter by date and status
  - Pin table (pin, source module, record, asset, severity, status, date)
  - Revision overlay control
  - Record side drawer
- **actions**:
  - Place pin
  - Link pin to asset
  - Open record
  - Compare revisions
  - Carry forward or flag pins
  - Filter
- **access**: markup.view; each layer shown only if the user can see the source module; placing pins needs markup.pin

#### Revision overlay comparison `/viewer/:versionId/compare` (Markup, viewer & plan room)

Compare two drawing revisions and review pin carry-forward.

- **layout**: Overlay canvas with opacity slider and a pin review list.
- **sections**:
  - Overlay controls
  - Pins needing review list
- **actions**:
  - Carry forward pins
  - Flag for review
  - Swap revisions
- **access**: markup.view; carry-forward needs markup.pin

#### Stamp library admin `/settings/markup/stamps` (Markup, viewer & plan room)

Manage approved, rejected and custom stamp templates.

- **layout**: List with template editor and live preview.
- **sections**:
  - Stamp list
  - Template editor (text, colour, who/when/hash fields)
  - Preview
- **actions**:
  - Create
  - Edit
  - Disable
  - Delete
- **access**: markup.admin

#### Markup settings `/settings/markup` (Markup, viewer & plan room)

Control tools, colours, layers, GPS policy, flattening and offline drawing sets.

- **layout**: Tabbed settings form.
- **sections**:
  - Tools enabled
  - Status colours
  - Pin types and severity colours
  - Layer defaults per role
  - Strip GPS
  - Scale presets
  - Flatten triggers
  - Offline drawing set rules
  - Terminology labels
- **actions**:
  - Save
  - Reset
- **access**: markup.admin

#### Mobile plan and photo markup `/m/plans/:sheetId` (Markup, viewer & plan room)

Offline-capable drawing viewing, pin placement and photo markup in the field.

- **layout**: Mobile full-screen canvas with bottom toolbar and bottom-sheet pin detail.
- **sections**:
  - Cached drawing set
  - Pin placement
  - Photo capture and markup
  - Sync status
- **actions**:
  - Place pin
  - Annotate
  - Capture photo
  - Sync later
- **access**: markup.create; drawings must be cached for the scope
