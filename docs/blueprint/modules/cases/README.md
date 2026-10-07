# User-authored playbooks (`cases`)

- **Group:** Platform services
- **Phase:** removed

> **REMOVED by owner. Do not build. Strip any hooks that reference it.**

What it is
The owner has decided to remove the User-authored playbooks module as a standalone module. It was originally a Platform services module (suggested phase P4) in which teams wrote their own guided walkthroughs of how to use the platform. No advisor saw a v1 need for it. The owner's decision is final: the module is removed and no separate authoring tool is to be built. The relevant accepted suggestions are retained below as capabilities to be absorbed into document control and in-app help rather than delivered as a playbook product.

What it does
The intent that survives is limited to four accepted items. Customers can hold their own procedures and guides, for example how a CUI inspection is raised from asset selection through to NCR closure, as controlled procedures inside the document store with versioning and read-and-acknowledge tracking. Guides are written as simple Markdown whose terminology tokens pull the renamed terms for each market. A help button on a screen launches the relevant guide so field users get contextual help. Acknowledgements can be linked to competency records so that evidence that a person has read a procedure can feed the eligibility gate for relevant tasks.

Features
- Controlled procedures with read-and-acknowledge tracking (folded into document control; suits QMS and ISO 9001 audit needs; effort M)
- Markdown guides with terminology tokens (cheap first version that adopts each market's renamed terms; effort S)
- Guides launched from a screen with a help button (contextual help for tasks such as raising a CUI inspection; effort S)
- Link acknowledgements to competency records (acknowledgement evidence can feed the eligibility gate for relevant tasks; effort M)
- The original feature, Custom walkthroughs, is removed along with the module.

Interactions
- Documents with revisions: controlled procedures reuse the existing document store and revision control instead of a separate authoring tool.
- Users and projects: guide and procedure visibility is scoped by project and team.
- Terminology settings: Markdown guides use tokens resolved from project settings so they adapt per market (for example Kaefer on Rio Tinto remediation work versus other markets).
- Certificates and competency records: acknowledgements can be recorded as competency evidence feeding the task eligibility gate.
- Approval routes: the earlier advisor note suggested that controlled procedures could be published through approval routes. This is not confirmed by the owner (see Open questions).
- Screens: the help button appears on individual screens and opens the matching guide.

Data
No dedicated case, case assignment or completion tables are to be created. The earlier advisor proposal of a case record (title, audience, steps with text, screenshots and deep links, version, status), case assignment and completion record is not adopted as a separate model. Data needs are met by existing and extended structures:
- Document or procedure record with revisions (existing documents capability), holding Markdown content that may contain terminology tokens.
- Acknowledgement record: person, document revision, date and time.
- Link from an acknowledgement to a competency record.
- Mapping from a screen or context to a guide for the help button.

Pages
No playbook library, step editor or guide overlay pages are to be built. Surfaces needed:
- Existing document pages, extended to show procedures and acknowledgement status.
- A help button on screens that opens the relevant Markdown guide.
- Acknowledgement view showing who has and has not acknowledged the current revision.

Decisions and notes
- Owner decision: remove this module. This overrides the original suggestion of phase P4 and any plan for a separate authoring tool.
- Owner accepted four suggestions (listed under Features), which are to be folded into document control and in-app help.
- Competitor research noted that construction suites do not usually offer user-authored scenarios, and that the idea overlaps with forms, ITP templates and document control. In-app guidance tools such as Pendo, WalkMe and Appcues and vendor academies cover the general need.
- Market abilities seen but not accepted, and therefore not specified: highlighted screen element tours, role-based onboarding tours, guide usage analytics and drop-off, workflow templates, and assignment of training with due dates.
- Low priority for v1; the first version can be simple Markdown pages.

Open questions
- Should controlled procedures be published through approval routes before becoming current, as the feature and integration designer suggested? The owner has not decided.
- Which task types should check acknowledgement-based competency in the eligibility gate?
- Which phase should the folded-in capabilities be delivered in, now that P4 no longer applies?

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
