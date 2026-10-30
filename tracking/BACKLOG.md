# Backlog: work deliberately left out of R1

Everything PLAN-R1 (2026-10-18) found in the R1 modules' READMEs and data models, in the owner's carried-forward
answers, or in the pass-B authors' notes, that has **no row in the R1 section of [BOARD.md](BOARD.md)**. Nothing here is
lost: the PLAN-P2 generator, or a later `PLAN-*` task, starts from this list.

- **Why it waits** says what deferred it: ADR 0007 §4–5 (not in the R1 cut; "defer by default" until a paying customer or
  a need shown in the pilot), an open owner question (`#N` in [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md)), or a module
  that does not exist yet.
- **Pull an item into R1** only with the owner's say-so: add a board row and a stub, and strike the line here with the
  new task ID.
- Decisions behind this list: [ADR 0036](../docs/adr/0036-r1-module-decisions.md).

## Platform and cross-cutting

| Item | Source | Why it waits |
|---|---|---|
| Offline field PWA and sync, with its property tests (TESTING-07, now in "Later (P2+)") | ADR 0007 §4, owner 2026-10-10 | Offline is out of R1; adding it moves R1 by about 6–8 weeks |
| Offline rules: two clocks, 24-hour sync grace, 7-day online validation, session interlock, encrypted store, evidence-pending attachments | ADR 0010 addendum part 3 | Built with the offline module |
| Offline provisional hold-point release and the PIN-only project setting in the field app | ADR 0010 addendum, IDENTITY-07 | Built with the offline module (PROJECTS-04 adds the setting itself) |
| Remote un-block and targeted wipe: check-out token, pre-sync commands, quarantine store, targeted purge, "revoke device", admin page | ADR 0024, OPEN-QUESTIONS #31 | Offline module; #31 still open |
| Customer-owned Power BI `reporting_feed` add-on | ADR 0008 C | Needs its own security review and ADR first |
| `ai_gov` tasks for the `AiProvider` port (Bedrock adapter first) | ADR 0019 | Not in R1 |
| Siloed deployment option for Enterprise | ADR 0008 D | Only on a contract, after R1 |
| Sealed archive bundle and read-only archive viewer | ADR 0022 point 6 | After R1 and after TENANCY-07 |
| Dedicated client app (ITP sign-off, scheduling, report coding) | ADR 0010 addendum part 2 | The R1 portal is its first version |
| Form designer (three-pane builder, logic builder, print and mobile preview, test console) and its foundation (custom, react-jsonschema-form or SurveyJS) | forms README, ADR 0007 §4 | No designer in R1; templates are JSON |
| Asset-level hold flag and NCR escalation to variations or change orders | issues README | No variations module in R1 |
| Glossary tooltips and search-query expansion with term aliases | TERMS-06 (original), ADR 0036 §6 | Waits for a search module |
| Policy-free read of approvals history for host modules (so reports can print the whole decision chain) | REPORTS-03 author | R1 reports print the final approver from the event |
| Shared list-cursor helper adopted by projects (`aip/platform/http/cursor.py` from ASSETS-01) | ASSETS-01 author | A projects tidy-up after ASSETS-01 |
| Playwright API project and a seeded inspection journey on the compose stack | several pass-B authors | API-only R1 rows prove their HTTP journeys in integration tests; the page rows carry browser e2e |

## Assets

| Item | Source | Why it waits |
|---|---|---|
| Risk-based inspection scheduling per asset class, due dates and overdue alerts (`rbi_schedules`) | README, data model | ADR 0007 §4–5 |
| Line/circuit and P&ID linkage with clickable tags on drawings (`asset_drawing_links`) | README | ADR 0007 §4–5 |
| QR, barcode and RFID tags; scan to open (`asset_tags`) | README | ADR 0007 §4–5 |
| Printable QR/RFID label sheets through the report engine | README | ADR 0007 §4–5 |
| Asset history merge, split and retag with lineage (`asset_lineage`) | README | ADR 0007 §4–5 |
| CUI condition model with promoted corrosion grade, criticality, custom status with neutral state, GPS location | README, ASSETS-01 author | Status and neutral state wait on ITEMTYPES-05 (#40); the rest is not in the R1 cut |
| Open-item counts per tree node | README | Needs inspections and issues counts first |
| Modules vs items vs components rules under item types | README | Not in the R1 cut |
| Drag-and-drop reparent in the tree (R1 has a keyboard Move dialog) | ASSETS-03 author | Not needed for R1 |
| Asset condition analytics and defect trends | README | ADR 0007 §4–5 |
| Asset notifications (import, overdue, moved, certificate expiring, label sheet ready) | README | No notifications module in R1 |
| "Used in" reverse lookup on register items | README | After ASSETS-06 |

## Item types

| Item | Source | Why it waits |
|---|---|---|
| Type inheritance (base and extended types), add and tighten only (ADR 0039) | README, #38 | Not in the R1 cut |
| Migration preview with impact counts when a schema changes (ADR 0039) | README, #39 | Not in the R1 cut; R1 pins versions |
| Auto-create an ITP or inspection per item type, with default templates | README, ITEMTYPES-01 author | Not in the R1 cut |
| Units and tolerances on measurements with out-of-range flags for the rules engine | README | No rules engine in R1 |
| Conditional and calculated item attributes | README | Forms gets calculated fields first (FORMS-07) |
| Shared attributes registry with merge suggestions (`attributes`) | README | Not in the R1 cut |
| Deprecating an item type while assets still use it | ITEMTYPES-01 author | Not in the R1 cut |
| Default attribute schema per content type; icon upload; drag reordering of content types | README, data model | Not in the R1 cut |
| Display units beyond the SI storage units (for example µm for DFT) | FORMS-01 author | Needs a terms units change |

## Forms

| Item | Source | Why it waits |
|---|---|---|
| Per-field client visibility (hide answers from the client report) | REPORTS-03 author | Not in the R1 cut; the client variant hides names and ids only |
| Instrument reference with calibration check at answer time | README | Needs equipment certificates in eligibility first |
| Required competency and default frequency per template | README, data model | Competency matrix is after R1 |
| Context auto-fill and prefilled fields | README | Not in the R1 cut |
| Test-fill and publish checks on sample answers | README | Not in the R1 cut |
| Print-accurate report slot mapping | README | Report templates map data in R1 |
| Spreadsheet or PDF template import assistant (AI-assisted) | README | Needs the AI gateway |
| Optional approval workflow for template revisions | README | Not in the R1 cut |
| RFI, permit and test-report template kinds | README | Not in the R1 cut |

## Inspections

| Item | Source | Why it waits |
|---|---|---|
| Customer and inspector scheduling: calendar, invitations, reminders, reschedule (`inspection_bookings`, `booking_attendees`) | README, data model | Not in the R1 cut |
| Inspection programmes: frequency, next due, triggers (`inspection_programmes`) | README, data model | Not in the R1 cut |
| Competency-aware assignment suggestions (`inspection_assignments`) | README, data model | Needs the competency matrix |
| Surveillance points with sampling | README | Not in the R1 cut |
| Coverage and backlog dashboard | README | No dashboards module in R1 |
| Design-side supervision visits | README | Not in the R1 cut |
| Human-readable inspection reference numbers | INSPECTIONS-01 author | Needs a numbering decision |
| Editing or deleting ITP steps after creation; one child inspection per step | INSPECTIONS-03 author | Not in the R1 cut |
| Inspection notifications (assignment, reminders, overdue, eligibility failure) | README | No notifications module in R1 |

## Eligibility

| Item | Source | Why it waits |
|---|---|---|
| Competency matrix with gap report (`competency_requirements`) | README, data model | Not in the R1 cut |
| Discipline gating at inspection-category level (`discipline_gates`) | README, data model | Not in the R1 cut |
| Crew and work-package eligibility pre-check | README | Not in the R1 cut |
| Calibration schedule and quarantine status for instruments | README | Not in the R1 cut |
| Project register of credentials (licences, insurance, bonds, permits) and company, material-batch and project owner kinds | README, ELIGIBILITY-01 author | R1 owners are people and assets |
| Per-type grace periods; verification of licences against issuing registers | README, #44 | Open question |
| `required_fields` per certificate type | ELIGIBILITY-01 author | Not in the R1 cut |

## Scope of work

| Item | Source | Why it waits |
|---|---|---|
| Scope Portal WBS grid with blade and the v2 KPI strip | README | Not in the R1 cut |
| Cross-RSW task reporting endpoint with saved views | README | Not in the R1 cut |
| RSW templates by asset class and environment | README | Not in the R1 cut |
| Constraints and readiness checklist per RSW | README | Not in the R1 cut |
| Quantity-based progress and earned value (m², metres, items) | README | Not in the R1 cut |
| Scope revision comparison and approval of scope changes tied to variations | README | No variations module in R1 |
| Bulk import and sync of scopes from client portal exports | README | After DATAIO-05 |
| Consumable and RFI requirements in the completion gate (recorded as not applicable in R1) | SCOPEWORK-02 author | No stock or RFI module in R1 |
| Computed deadlines from priority; RSW numbering schemes | README, SCOPEWORK-01 author | Deferred in the README |
| Commercial fields mapping tasks to cost codes | README | `cost_items` is a removed module (AGENTS.md) |

## Issues

| Item | Source | Why it waits |
|---|---|---|
| NCR disposition with engineering approval and sealed records | README, ISSUES-03 author | Sealing decided (ADR 0039); immutable storage is open (#49) |
| Overdue and SLA notifications with escalation, including overdue CAPA | README | No notifications module in R1 |
| Root-cause trend reports and cost of poor quality | README | QMS is not in R1 |
| Kanban board view and CAPA board | README | After ISSUES-04 |
| Sign-off assurance on `verify` and `close` | ISSUES-01 author | No issue transition is critical in R1 |
| Subcontractor responses to NCRs and portal scoping by responsible company | README | Portal R1 slice is client sign-off only |
| Raise an NCR from the v2 blade | README | No Scope Portal v2 in R1 |

## Report engine

| Item | Source | Why it waits |
|---|---|---|
| Approval adds a KMS-held PAdES signature to PDF reports, plus a verification page for PDFs and files (ADR 0039, #47–#48) | README | Not in the R1 cut; R1 records a sha256 |
| Immutable storage of issued PDFs | README, #49 | Open question |
| Publishing to a named distribution list with delivery receipts and expiring links (`published_records`, `delivery_receipts`, `delivery_access_log`) | README, data model | Not in the R1 cut |
| Report QA pre-flight through a rules engine | README | No rules engine in R1 |
| Domain blocks: thickness map, CUI condition and DFT charts | README | Not in the R1 cut |
| Data book compiler with bookmarks and cover sheets | README | Not in the R1 cut |
| Per-tenant and per-client branding | README | Not in the R1 cut |
| Template designer with live-data preview | README | Templates are data in R1 |
| Diary and meeting reports | README | No diary or meeting module in R1 |
| Page count recorded at render time | REPORTS-02 author | Needs a runtime PDF reader |

## Data import and export

| Item | Source | Why it waits |
|---|---|---|
| Register and whole-tenant export (Excel, CSV, JSON) with manifests and checksums | README | Tenant export is TENANCY-07; register CSV follows ADR 0033 per module |
| Restore or import-from-export | README, #50 | Open question |
| Dual approval for full exports; scheduled exports; project-scoped export | README, #51–#53 | Open questions |
| Handover data book export per asset subtree | README | After the report engine's data book |
| Mixed item types in one asset-tree import | DATAIO-02 author | One item type per import in R1 |
| Legal-hold check on batch rollback | DATAIO-02 author | Needs AUDIT-05 (legal hold) |

## Portal

| Item | Source | Why it waits |
|---|---|---|
| Share packs: time-limited read-only bundles without a full account | README | Not in the R1 portal slice (ADR 0036) |
| Subcontractor responses to issues and NCRs with evidence upload | README | Not in the R1 portal slice |
| Subcontractor onboarding gate on company and personnel certificates | README | Not in the R1 portal slice |
| Client read-only asset condition dashboard | README | Not in the R1 portal slice |
| Download watermarking and view-only mode | README | Not in the R1 portal slice |
| Per-client branding and terminology | README | Not in the R1 portal slice |
| Enterprise SSO for client users (SAML or OIDC federation) | README | Clients use local accounts in R1 (ADR 0010 addendum part 2) |
| In-app notification centre for expiry reminders (R1 sends email and shows expiry on the admin page) | PORTAL-08 | No notifications module in R1 |
| Magic-link sign-in and PIN credentials for portal users (`portal_credentials`) | README, ADR 0005 | Clients use local accounts in R1 (ADR 0010 addendum part 2) |
