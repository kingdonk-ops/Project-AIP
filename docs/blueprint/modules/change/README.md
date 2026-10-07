# Change orders, variations & MOC (basic) (`change`)

- **Group:** Commercial
- **Phase:** P3

What it is
Change orders, variations and MOC (basic) is the Commercial module for recording scope changes, their cost and time impact, and for formal management of change (MOC) on engineering changes. It is one change-record model with a type (change order, variation, MOC, discovered condition) and a shared workflow, not separate tables per concept. The owner has asked for it to be kept basic. Suggested phase is P3. It is not yet built in AIP.

What it does
A change starts from a notice, an instruction (including verbal instructions from the phone log), an RFI, or an inspection finding. It is priced against cost items, approved through the workflow engine and tracked to final account. Management of Change adds the process-industry review and approval of engineering changes. Terminology is tenant-configurable (Variation, Change Order, Client Instruction, Scope Change Notice) through the terminology dictionary, so each market and customer sees its own labels. The first customer is Kaefer on Rio Tinto remediation work.

Features
- Change register: source, description, asset, cost and time impact, status
- Variation lifecycle: notice > request > order > measured > final account
- Daywork sheets linked to field records
- Daywork sheet built from field records: pulls crew, hours, consumables and plant used from the diary, resources and the consumables ledger, then captures the client signature
- MOC: proposal, technical review, risk review, approval, implementation, close-out
- MOC checklist templates per discipline (engineering, integrity, HSE) with required reviewer roles and an open-action gate before close-out
- Approval through the workflow engine
- Contractual notice-clock tracker with time-bar warnings tied to each change record; tasks and escalation can use the same clock
- Verbal instruction capture that creates a draft change record, with a confirmation letter template
- Discovered-condition change type raised directly from an inspection finding, with photos and asset link (for example unexpected CUI or corrosion under insulation)
- Links to correspondence, diary, phone log and RFIs
- Tenant-configurable terminology and labels

Interactions
- Cost items and schedule of rates (thin): pricing of change lines; replaces any BOQ dependency
- Workflow and approvals engine: approval routes and sign-off
- Claims evidence pack (basic): evidence chronology
- Transmittals and correspondence: notices and confirmation letters
- Voice notes and phone log: verbal instructions
- Terminology dictionary and localisation: renamable labels
- Inspections: discovered-condition changes raised from findings
- Diary, resources and consumables ledger: source data for daywork sheets
- Documents: supporting files and attachments
- Notifications and reporting: receive changeorder.submitted and changeorder.approved events

Data
- Change record: number, type, reason or source, description, optional asset_id, cost impact, time impact, status, contract reference, notice deadline
- Change lines linked to cost items
- Approvals and approval trail
- Lifecycle stage and timeline entries
- Daywork sheet: labour, plant and material, with client signature
- MOC record: review stages, checklist items, required reviewer roles, open actions
- Notice clock: period per contract, start event, deadline, warning state
- Attachments through documents

Pages
- Change list or register with a stage pipeline from notice to final account, under Commercial
- Change detail with timeline, cost items table, attachments and approval trail
- Submit and approve actions
- Daywork sheet capture with client signature
- MOC detail with checklist and review stages
- Labels follow tenant terminology

Decisions and notes
- Owner: Change Orders is Basic.
- One change model with tenant-configurable labels, not separate change order, variation and MOC tables.
- Cost items replace the BOQ link.
- Approvals run through the workflow engine.
- All five suggested features (notice clock, daywork from field records, verbal instruction capture, discovered-condition type, MOC checklists) are accepted.
- Notice periods are configurable per contract rather than hard-coded to one contract form.
- Competitors (Procore, Oracle Unifier, Aconex, InEight and others) are strong on cost impact and multi-tier approval but project-centric with fixed terms. The differentiators here are configurable terminology and links to asset, inspection and diary evidence.

Open questions
- Contract forms: should the module ship configurable templates for AS 4000, NEC and FIDIC clause names and notice periods, or only per-contract configurable periods? This conflicts with keeping the module basic and is not yet decided.
- Scope depth: should disruption and extension-of-time claims, site measurement records and multi-tier (client, head contractor, subcontractor) change orders be included, or left to a later phase? Not decided.
- Visibility: should commercial values be hidden from subcontractor roles? Suggested by an advisor, not decided.
- Should this module be the base of a wider change family hub? An advisor raised it; the owner has not decided.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
