# Certificates, competency & calibration gate (`eligibility`)

- **Group:** Inspection & quality
- **Phase:** P1

What it is
One service that answers whether a person, instrument or material is valid right now for a given step. It tracks every expiring qualification, calibration, permit, insurance and material use-by date, and blocks work that relies on something invalid. Certificates are a real list per register item (a UT gauge accumulates calibration certificates; a welder's ticket gets replaced). It merges the compliance documents, credentials and resource certification ideas into one model.

What it does
Expiry status is green, amber (under 30 days) or red, computed in query rather than stored. Referencing an expired item is hard-blocked. Items marked out of stock or unavailable are excluded from expiry feeds and reminders, evaluated at send time; if stock returns, the item reactivates. Other modules call the single check interface and never read certificate tables directly. Credential snapshots are stamped onto sign-offs so history proves who was qualified at the time.

Features
- Certificates per asset, person, equipment, company, material batch or project: type, number, issued, expiry, linked document, issuer, status valid/expired/superseded/revoked
- Expiry-date flag on any attribute field; computed green/amber/red
- Hard block on expired people or out-of-calibration equipment
- Audited override with named permission, reason, approver and expiry
- Exclude out-of-stock/unavailable items from expiry feeds and reminders (owner rule); must not hide expired items still in use
- Expiring-soon feed grouped by window, with configurable reminder windows and supervisor escalation (for example 60/30/7 days)
- Project register of credentials a delivery relies on: licences, memberships, professional indemnity, insurance, bonds, permits
- Discipline gating and expired-certificate block at inspection category level
- Competency matrix per person and per template requirement, with gap report
- Crew and work-package eligibility pre-check
- Calibration schedule and quarantine (out-for-calibration) status for instruments

Interactions
- Inspections, ITPs & hold points: checked before signing a step
- Traceability graph: validity at time of use
- Stock, consumables & materials: availability suppresses expiry alerts
- Equipment & fleet: calibration certificates
- Users, sign-in & SSO: qualifications on person records
- Tasks, deadlines & my work: reminders feed the my-work queue

Data
Migrate the existing certificates table by adding certificate_type_id, owner_kind, owner_id and superseded_by. certificate_types holds code, renamable name, owner_kind, requires_expiry, amber_days (default 30), reminder_offsets, required_fields and suppress_when_unavailable. Also competency_requirements, overrides and reminder_log. Availability is read from an event cache at send time. Events consumed include inventory.availability_changed, equipment.created, user.qualification_changed, document.revised.

Pages
- Compliance register (/compliance)
- Expiring-soon feed (/compliance/expiring) with suppression indicator toggle
- Add certificate (/compliance/new)
- Certificate detail (/compliance/:id): history, reminders, items relying, suppression state, eligibility result, audit trail
- Competency matrix (/compliance/matrix)
- Override requests queue for the quality manager

Decisions and notes
- Owner rule: if a product has a use-by date but is not in stock or unavailable, do not show its expiry and do not notify people beforehand.
- Owner accepted all six suggestions listed above.
- Overrides need a named permission, reason and audit entry.
- Use AWST time zone handling and test expiry boundaries; test that a status change cancels pending reminders.
- Terminology (Certificate, Ticket, Licence) is renamable.
- Built in AIP: expiry flag and badges, hard block, certificates list, inspection categories and discipline gating.

Open questions
- Reminder scheduling tool: advisor suggested BullMQ, while the repo stack is Python FastAPI; the job mechanism is undecided.
- Grace periods per type and verification of licences against issuing registers were seen in the market but not decided.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
