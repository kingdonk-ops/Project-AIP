# RFIs & submittals (`rfi_submittals`)

- **Group:** Collaboration & coordination
- **Phase:** P3

What it is
RFIs and submittals is the collaboration module for formal questions to the client or designer (Request For Information) and for contractor submissions that go through review. It is asset-anchored: every RFI and submittal can be tied to an asset node and its inspection or NCR history. The module aims for parity with Procore, ACC, Aconex, Unifier, InEight, Trimble Viewpoint and Dalux on workflow, impact tracking and drawing links, and adds asset anchoring, inspection-paperwork submittal types, enforced gates and tenant terminology. It is not built as a standalone differentiator. Suggested phase P3. Collaboration and coordination group.

What it does
RFIs carry a question, discipline, asset and drawing references, due date and response, with cost and schedule impact flags. Submittals (shop drawings, product data, method statements, certificates, warranties, test reports) track review status and resubmissions. Both are filterable by asset subtree. An inspector can see open RFIs and submittals on any asset and their effect on pending inspections, so an unresolved design query is visible before a hold-point release is attempted. Required submittals can block an inspection or work-scope task until an accepted review code is reached, consistent with AIP's existing completion gates.

Features
- RFI: number, question, discipline, asset(s), package, drawing and document references, raised by, ball-in-court, due date, status, response, cost and schedule impact flags
- RFI actions: raise, assign, respond, accept/reject, close, convert to variation
- Convert RFI to variation candidate with pre-filled references, impact notes and attachments, preserving the evidence trail
- Submittal register with types, spec reference, asset/package, revision, required-by date and review codes
- Review outcome codes such as approved, approved as noted, revise and resubmit, rejected; codes are tenant-configurable
- Submittal actions: create, submit, review, return, resubmit, close
- Resubmission history and a resubmission comparison
- Submittal types for inspection paperwork: weld procedures, NDT procedures, personnel qualifications, calibration records and ITP approvals
- Gate rule: block an inspection or work-scope task until a required submittal (such as an approved NDT procedure) reaches an accepted review code
- Linked documents and markups, including photo markup on the RFI form
- Asset-subtree filtering and asset-node view of open RFIs and submittals with their effect on pending inspections
- Ageing columns and overdue tracking
- Response-time analytics by party, discipline and asset area
- Terminology switch for the word RFI: configurable labels (Request for Information, Technical Query, Query, TQ), numbering also tenant-configurable, kept distinct from Request for Inspection hold points with a clear disambiguating prefix in cross-module lists

Interactions
- Document library & control: attachments, file versions for revisions
- Change orders, variations & MOC (basic): flagged impacts start a candidate change or variation
- Tasks, deadlines & my work: due dates and review deadlines are written as deadlines
- Terminology dictionary & localisation: the meaning and label of RFI differ by market
- Contacts, plan room and markups: read for references and parties
- Approval routes: define the review sequence for submittals
- Notifications and timeline: assignment, response and review events
- Collaboration: comment threads
- Inspections, ITP hold points and RSW scopes: gate checks and the certificate gate
- Closeout and commissioning, handover dossiers: approved certificates and data packs pass through
- Procurement: long-lead links
- Meetings agendas, reporting and erp_chat: queries such as overdue RFIs on this unit

Data
- RFI: number, asset_id(s), package, question, discipline, raised by, ball-in-court, due date, status, cost and schedule impact flags
- Response
- Drawing/document reference
- Impact estimate
- Submittal: spec reference, type, asset/package, revision, required-by date
- Review step: reviewer, outcome code
- Resubmission history
- Attachments

Pages
- RFI register with ageing column and filters by asset subtree and status
- RFI form with attachments and photo markup
- RFI detail page with question and response thread and drawing cross-references, plus a response/review view
- Submittal register with ageing
- Review workspace beside the document viewer
- Resubmission comparison
- Asset-node panel of open RFIs and submittals
- Response-time analytics view
Layout sits under Documents and Records.

Decisions and notes
- AIP's 'RFI' hold point is an inspection kind (Request For Inspection), different from this module's Request For Information. Naming is reconciled through the terminology switch and a disambiguating prefix in cross-module lists.
- Owner accepted all six scout suggestions: terminology switch, asset-node linkage, inspection-paperwork submittal types, submittal gate rule, response-time analytics, convert RFI to variation candidate.
- Hold to market parity plus asset anchoring and tenant terminology.
- First customer is Kaefer on Rio Tinto remediation work.

Open questions
- Bulk import of submittal registers from spreadsheets and multi-reviewer consolidated responses were seen in the market but not decided by the owner.
- Automatic reminders for overdue items were seen in the market but not decided by the owner.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
