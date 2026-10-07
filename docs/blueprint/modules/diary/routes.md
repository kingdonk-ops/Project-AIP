# Page specs for `diary`

#### Diary register `/projects/:projectId/diary` (Site diary & field reports)

List all diary days with status, seal state and key counts.

- **layout**: Full-width DataTable with a filter bar, a month strip above the table and a right-hand preview drawer.
- **sections**:
  - Filter bar (date range, site, status, shift)
  - Diary days table (date, site, status, weather, workforce, plant, delays, events, amendments, sealed at/by)
  - Missing-day indicators
  - Bulk action bar
- **actions**:
  - Create today's diary
  - Open day
  - Export sealed days as PDF bundle
  - Send daily field report
  - Remind contributors
  - Saved views
- **access**: Project members with diary.view; create needs diary.create; bulk send and export need diary.report.

#### Open diary day `/projects/:projectId/diary/new` (Site diary & field reports)

Create a diary day for a site and date.

- **layout**: Modal or narrow single-column form.
- **sections**:
  - Project, site, date, shift
  - Copy labour and plant from previous day option
  - Duplicate-day warning
- **actions**:
  - Create
  - Create and open
  - Cancel
- **access**: Supervisors and site engineers with diary.create.

#### Diary day detail `/projects/:projectId/diary/:date` (Site diary & field reports)

Record the day and move it through submit and seal.

- **layout**: Sticky header with status and seal badge. Left section navigator, centre scrolling sections, right rail for links and contributors.
- **sections**:
  - Header (date, project, site, status, seal state)
  - Weather (auto-fetched, source, override)
  - Labour on site
  - Plant on site
  - Events
  - Instructions received
  - Delays (cause, hours)
  - Deliveries from logistics
  - Photos, video and drone captures
  - Linked RSWs, inspections and incidents of the day
  - Contributors and sign-offs
  - Seal and verification (hash, timestamp, signer, PDF)
  - Amendments
  - Daily field report preview
  - Activity and audit
- **actions**:
  - Add entry
  - Supersede entry
  - Attach media
  - Link RSW, inspection or incident
  - Prefill from resources and equipment
  - Submit for seal
  - Countersign
  - Seal day
  - Download sealed PDF
  - Verify seal
  - Add addendum after seal
  - Preview report
- **access**: View: diary.view. Edit entries while open: diary.edit or field grant. Seal: designated signer roles. Addenda: diary.amend.

#### Sign-off and seal `/projects/:projectId/diary/:date/seal` (Site diary & field reports)

Review completeness, sign and seal the day.

- **layout**: Stepper with checklist on the left and read-only PDF preview on the right.
- **sections**:
  - Required-sections checklist
  - Outstanding contributor submissions
  - Signer and countersigner panel
  - Seal payload preview with hash
  - Trusted timestamp result
- **actions**:
  - Sign
  - Countersign
  - Seal
  - Return to open
- **access**: Seal signer roles only, with MFA step-up.

#### Amendments and supersede history `/projects/:projectId/diary/:date/amendments` (Site diary & field reports)

Show the supersede chain and post-seal addenda.

- **layout**: Timeline with side-by-side original and superseding entries.
- **sections**:
  - Chain of entries with author, time, reason
  - Diff view
  - Addenda list with signer
- **actions**:
  - Add addendum
  - Export chain
  - Verify chain hash
- **access**: diary.view; add addendum needs diary.amend.

#### Daily field reports `/projects/:projectId/diary/reports` (Site diary & field reports)

Preview, send and track client daily reports.

- **layout**: Two-pane list and preview.
- **sections**:
  - Report list by date and send status
  - Template preview
  - Distribution list and delivery log
- **actions**:
  - Generate
  - Send
  - Resend
  - Download PDF
- **access**: diary.report; clients view via the portal if shared.

#### Diary calendar `/projects/:projectId/diary/calendar` (Site diary & field reports)

See completeness and seal state across the month.

- **layout**: Month calendar with colour-coded days.
- **sections**:
  - Day cells (open, submitted, sealed, missing)
  - Legend
  - Delay and incident markers
- **actions**:
  - Open day
  - Create missing day
  - Switch site or shift
- **access**: diary.view.

#### Diary settings `/projects/:projectId/diary/settings` (Site diary & field reports)

Configure cut-offs, required sections, weather, access defaults and seal rules.

- **layout**: Tabbed settings form.
- **sections**:
  - Cut-off and auto-seal time
  - Required sections
  - Weather provider and override rules
  - Entry categories and delay causes
  - Field access defaults (expiry, PIN length, device binding)
  - Seal signers and countersign
  - Report template and distribution
  - Retention and legal hold
  - Prefill sources
  - Terminology keys
- **actions**:
  - Save
  - Reset to defaults
  - Preview report template
- **access**: Project admin with diary.configure.

#### Mobile diary (field and offline) `/m/diary/:date` (Site diary & field reports)

Quick capture by supervisors and PIN or magic-link contributors.

- **layout**: Single-column PWA with a bottom tab bar, large touch targets and a sync status chip.
- **sections**:
  - Today card
  - Section tiles (weather, labour, plant, events, delays, photos)
  - Camera and media capture
  - Offline queue and conflict list
- **actions**:
  - Add note
  - Take photo
  - Record delay
  - Submit my contribution
  - Sync now
  - Resolve conflict
- **access**: Full users, or PIN/magic-link principals with a diary grant for named projects. No access to other modules.

#### Field link landing `/field/access/:token` (Site diary & field reports)

Confirm magic-link or PIN entry safely.

- **layout**: Minimal centred page on the separate portal origin.
- **sections**:
  - Project and scope of access
  - PIN entry
  - Device binding notice
  - Confirm button (POST)
- **actions**:
  - Confirm and enter
  - Request new link
- **access**: Holders of a valid single-use link.
