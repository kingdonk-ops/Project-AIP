# Blueprint index

The original 2.5 MB blueprint, split so an agent only reads what its current task needs.

## Reference files (read on demand)

| File | Read when |
|---|---|
| [00-brief.md](00-brief.md) | Product context: audience, compliance, scale |
| [01-decisions.md](01-decisions.md) | Choosing a library or approach (owner decisions win) |
| [02-advisor-summaries.md](02-advisor-summaries.md) | Background rationale only |
| [03-site-hierarchy.md](03-site-hierarchy.md) | Building navigation or the app shell |
| [04-code-layout.md](04-code-layout.md) | Creating a module folder (Python-era, see warning) |
| [05-access-matrix.md](05-access-matrix.md) | Adding roles or permissions |
| [06-build-order.md](06-build-order.md) | Phase goals and exit criteria |
| [07-task-conventions.md](07-task-conventions.md) | **Every task**: definition of done |
| [pages-global.md](pages-global.md) | Auth, shell, profile and error pages |

## Modules (by phase)

| Phase | Module | Group | Folder |
|---|---|---|---|
| P0 | Workflow & approvals engine | Documents & records | [`modules/approvals/`](modules/approvals/README.md) |
| P0 | Upload & file processing pipeline | Documents & records | [`modules/uploads/`](modules/uploads/README.md) |
| P0 | Architecture & module boundaries | Foundations & architecture | [`modules/arch/`](modules/arch/README.md) |
| P0 | Database & schema conventions | Foundations & architecture | [`modules/database/`](modules/database/README.md) |
| P0 | Design system & app shell | Foundations & architecture | [`modules/design/`](modules/design/README.md) |
| P0 | Operations, hosting & deployment | Foundations & architecture | [`modules/ops/`](modules/ops/README.md) |
| P0 | Security & compliance programme | Foundations & architecture | [`modules/security/`](modules/security/README.md) |
| P0 | Tech stack | Foundations & architecture | [`modules/stack/`](modules/stack/README.md) |
| P0 | Tenancy, organisations & data residency | Foundations & architecture | [`modules/tenancy/`](modules/tenancy/README.md) |
| P0 | Terminology dictionary & localisation | Foundations & architecture | [`modules/terms/`](modules/terms/README.md) |
| P0 | Testing & quality engineering | Foundations & architecture | [`modules/testing/`](modules/testing/README.md) |
| P0 | Roles, permissions & teams | Identity, access & tenancy | [`modules/access/`](modules/access/README.md) |
| P0 | Users, sign-in & SSO | Identity, access & tenancy | [`modules/identity/`](modules/identity/README.md) |
| P0 | Projects, sites & classification | Identity, access & tenancy | [`modules/projects/`](modules/projects/README.md) |
| P0 | Audit trail, activity & timeline | Reporting, search & AI | [`modules/audit/`](modules/audit/README.md) |
| P1 | Asset hierarchy & registers | Asset core | [`modules/assets/`](modules/assets/README.md) |
| P1 | Traceability graph: components, materials & certificates | Asset core | [`modules/components/`](modules/components/README.md) |
| P1 | Content types, item types & attributes | Asset core | [`modules/item_types/`](modules/item_types/README.md) |
| P1 | Scopes of work (RSW), disciplines & tasks | Asset core | [`modules/scope_work/`](modules/scope_work/README.md) |
| P1 | Comments, mentions & notifications | Collaboration & coordination | [`modules/comments/`](modules/comments/README.md) |
| P1 | Tasks, deadlines & my work | Collaboration & coordination | [`modules/tasks/`](modules/tasks/README.md) |
| P1 | Contacts & companies | Commercial | [`modules/contacts/`](modules/contacts/README.md) |
| P1 | Document library & control | Documents & records | [`modules/documents/`](modules/documents/README.md) |
| P1 | Equipment & fleet | Field operations | [`modules/equipment/`](modules/equipment/README.md) |
| P1 | Stock, consumables & materials | Field operations | [`modules/inventory/`](modules/inventory/README.md) |
| P1 | Certificates, competency & calibration gate | Inspection & quality | [`modules/eligibility/`](modules/eligibility/README.md) |
| P1 | Form & template designer | Inspection & quality | [`modules/forms/`](modules/forms/README.md) |
| P1 | Inspections, ITPs & hold points | Inspection & quality | [`modules/inspections/`](modules/inspections/README.md) |
| P1 | Issues, NCRs & corrective actions | Inspection & quality | [`modules/issues/`](modules/issues/README.md) |
| P1 | Rules & validation engine | Inspection & quality | [`modules/rules/`](modules/rules/README.md) |
| P1 | Data import, export & backup | Platform services | [`modules/data_io/`](modules/data_io/README.md) |
| P2 | Offline field app & sync | Asset core | [`modules/offline/`](modules/offline/README.md) |
| P2 | Markup, viewer & plan room | Documents & records | [`modules/markup/`](modules/markup/README.md) |
| P2 | E-signatures & tamper-evident records | Documents & records | [`modules/signing/`](modules/signing/README.md) |
| P2 | Transmittals & correspondence | Documents & records | [`modules/transmittals/`](modules/transmittals/README.md) |
| P2 | Site diary & field reports | Field operations | [`modules/diary/`](modules/diary/README.md) |
| P2 | Resources & crews (basic) | Field operations | [`modules/resources/`](modules/resources/README.md) |
| P2 | Schedule & look-ahead (basic) | Field operations | [`modules/schedule/`](modules/schedule/README.md) |
| P2 | Handover, data books & submissions | Handover & asset lifecycle | [`modules/handover/`](modules/handover/README.md) |
| P2 | Client & subcontractor portal | Identity, access & tenancy | [`modules/portal/`](modules/portal/README.md) |
| P2 | Punch list & defects liability | Inspection & quality | [`modules/punchlist/`](modules/punchlist/README.md) |
| P2 | Quality roll-up & audits | Inspection & quality | [`modules/qms/`](modules/qms/README.md) |
| P2 | Report engine & published records | Inspection & quality | [`modules/report_engine/`](modules/report_engine/README.md) |
| P2 | Search, retrieval & saved views | Reporting, search & AI | [`modules/search/`](modules/search/README.md) |
| P2 | Safety & HSE | Safety & compliance | [`modules/safety/`](modules/safety/README.md) |
| P3 | RFIs & submittals | Collaboration & coordination | [`modules/rfi_submittals/`](modules/rfi_submittals/README.md) |
| P3 | Change orders, variations & MOC (basic) | Commercial | [`modules/change/`](modules/change/README.md) |
| P3 | Supplier catalogue, requisitions & POs | Commercial | [`modules/procurement/`](modules/procurement/README.md) |
| P3 | Inbound capture & connectors | Documents & records | [`modules/ingestion/`](modules/ingestion/README.md) |
| P3 | Site logistics & mobilisation | Field operations | [`modules/logistics/`](modules/logistics/README.md) |
| P3 | Integrations & webhooks | Platform services | [`modules/integrations/`](modules/integrations/README.md) |
| P3 | Dashboards & KPI reporting | Reporting, search & AI | [`modules/reporting/`](modules/reporting/README.md) |
| P3 | Temporary works register | Safety & compliance | [`modules/temporary_works/`](modules/temporary_works/README.md) |
| P4 | Interface management | Collaboration & coordination | [`modules/interfaces/`](modules/interfaces/README.md) |
| P4 | Meetings & AI minutes | Collaboration & coordination | [`modules/meetings/`](modules/meetings/README.md) |
| P4 | Regional reference data packs | Commercial | [`modules/ref_packs/`](modules/ref_packs/README.md) |
| P4 | Voice notes & phone log | Field operations | [`modules/voice_phone/`](modules/voice_phone/README.md) |
| P4 | AI governance & data controls | Foundations & architecture | [`modules/ai_gov/`](modules/ai_gov/README.md) |
| P4 | Prefab & off-site manufacture | Handover & asset lifecycle | [`modules/prefab/`](modules/prefab/README.md) |
| P4 | Service & maintenance | Handover & asset lifecycle | [`modules/service/`](modules/service/README.md) |
| P4 | Commissioning | Inspection & quality | [`modules/commissioning/`](modules/commissioning/README.md) |
| P4 | AI assistant & agents | Reporting, search & AI | [`modules/ai_assistant/`](modules/ai_assistant/README.md) |
| removed | Cost items & schedule of rates (thin) | Commercial | [`modules/cost_items/`](modules/cost_items/README.md) |
| removed | User-authored playbooks | Platform services | [`modules/cases/`](modules/cases/README.md) |
