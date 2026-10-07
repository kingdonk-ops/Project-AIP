# Tasks, deadlines & my work (`tasks`)

- **Group:** Collaboration & coordination
- **Phase:** P1

What it is
Tasks, deadlines & my work is the single queue for everything a person needs to do in AIP, with overdue escalation. It sits in the Collaboration & coordination group and is suggested for phase P1. It combines a home 'My Work' queue, simple tasks with checklists, and a cross-module deadline register that notifies owners and escalates to managers after a grace period. Every task can attach to an asset node or source record, so context is never lost. General trackers (Procore, ACC Issues, Fieldwire, Dalux, Asana, Monday.com, Jira, Planner) do assignment, due dates and notifications well and are table stakes; the differentiator here is the link to assets, inspections and approvals, automatic task creation, and one register of due dates across modules.

What it does
- Gathers approvals awaiting me, inspections to sign, overdue items, mentions and expiring certificates into one home queue with inline actions.
- Lets people create simple tasks with a checklist, assignee, due date, priority and optional asset.
- Sweeps every module's due dates into a deadline register, notifies owners, then escalates to managers after the grace period.
- Raises tasks automatically from events in other modules.
- Routes approvals and sign-offs to a delegate when someone is away.
- Works offline in the field and syncs later.
- Closing the source record resolves its deadline automatically.

Features
- My Work queue with inline actions (Approve, Open, Sign).
- Simple tasks with checklist, assignee, due date, priority, status and optional asset_id; personal to-dos; quick-add.
- Deadline register across modules with grace period and escalation. Actions: acknowledge, reassign, extend with reason, resolve.
- Overdue report and due-soon widget.
- Auto-task rules engine: raise tasks from hold-point reached, NCR opened, certificate expiring, calibration due, rejected inspection.
- Delegation and out-of-office routing for approvals and sign-offs, with date range and audit record.
- Roster- and calendar-aware deadlines: project calendar, public holidays by region, shutdown periods, so grace periods and escalations respect FIFO/DIDO rosters and WA/regional holidays.
- Asset-subtree task board and recurring task templates (for example weekly CUI strip-and-inspect checks per area).
- Offline task capture and completion with sync, including photo attachment and queued actions.
- Overdue and ageing analytics by source module, team and escalation level, exportable.
- Expiry feeds exclude items that are unavailable.

Interactions
- Comments, mentions & notifications: notifications and mentions; the deadline sweep reuses the notification service for owner reminders and manager escalation. Comments and attachments use shared services.
- Inspections, ITPs & hold points: inspections due, hold-point reached and rejected inspections create tasks.
- Certificates, competency & calibration gate: expiries and calibration due feed the register and create tasks.
- Workflow & approvals engine: approvals awaiting me; status workflow comes from the shared state engine.
- Other sources register and update deadlines or create tasks: NCRs, RFIs, submittals, meeting actions, voice drafts, punchlist, interface management, schedule commitments and MOC actions.
- Overdue counts feed reporting, dashboards and project intelligence; escalations write to the timeline; completion events are surfaced in reporting.

Data
- Task: title, assignee, due date, priority, status, optional asset_id, source record link, checklist items.
- Deadline: source record type and id, asset, owner, due date, grace period, escalation manager, status, snooze reason.
- Escalation log.
- Delegation record: delegator, delegate, date range, audit trail.
- Auto-task rule and recurring task template.
- Policy settings for grace and escalation per deadline type.
- Calendar data: project calendar, regional public holidays, shutdown periods.
- Topic and Decision records were proposed by an earlier advisor and are not confirmed.

Pages
- My Work (home queue).
- My Tasks and my deadlines.
- Project and asset-subtree task board.
- Team and project overdue board.
- Overdue and ageing analytics with export.
- Policy admin for grace, escalation and auto-task rules.
- Delegation settings.
- Quick-add and the dashboard due-soon widget.

Decisions and notes
- AIP already has a dashboard 'Due soon' (TASKS section 9.2); extend it rather than replace it.
- Extensions are audited because they can be contractual evidence.
- The owner accepted all six scout suggestions listed under Features.
- Terminology must be renamable per market.
- Other advisor-suggested items not accepted by the owner (for example multi-stage escalation ladders, digest emails with quiet hours, calendar and workload views) are not included.

Open questions
- Should the first release include statutory clocks, as one researcher suggested, or only grace-period escalation?
- Is the sweep built on BullMQ as one advisor proposed, or on the existing AIP Python backend stack (FastAPI with scheduled jobs)?
- Should Topic and Decision records live in this module or in meetings?

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
