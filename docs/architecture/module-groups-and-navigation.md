# Module groups and navigation

Overlay for [ADR 0018](../adr/0018-module-groups-and-navigation.md) (proposed). Documentation and menu design only: module names, folders and import rules do not change.

## Domain groups

- **Platform and foundations** (10): `arch`, `database`, `design`, `ops`, `ref_packs`, `security`, `stack`, `tenancy`, `terms`, `testing`
- **Identity and access** (3): `access`, `identity`, `portal`
- **Asset and work core** (8): `assets`, `commissioning`, `components`, `item_types`, `prefab`, `projects`, `scope_work`, `service`
- **Quality, inspection and HSE** (9): `eligibility`, `forms`, `inspections`, `issues`, `punchlist`, `qms`, `rules`, `safety`, `temporary_works`
- **Field, logistics and resources** (8): `diary`, `equipment`, `inventory`, `logistics`, `offline`, `resources`, `schedule`, `voice_phone`
- **Records, collaboration and intelligence** (24): `ai_assistant`, `ai_gov`, `approvals`, `audit`, `change`, `comments`, `contacts`, `data_io`, `documents`, `handover`, `ingestion`, `integrations`, `interfaces`, `markup`, `meetings`, `procurement`, `report_engine`, `reporting`, `rfi_submittals`, `search`, `signing`, `tasks`, `transmittals`, `uploads`

`cost_items` and `cases` stay removed.

## Menu

```
Work and assets          Assets (tabs: Components) · Item types · Scopes of work
Quality and compliance   Inspections and ITPs · Issues, NCRs and CAPA · Punch list · Quality roll-up
Field and execution      Site diary (voice and phone capture) · Schedule and look-ahead · Plant, materials and consumables
Documents and transmittals  Documents (markup and signing inside) · Transmittals · RFIs and submittals
Insight                  Dashboards and reports · Search · AI assistant
Settings (permission-gated)  Organisation and projects · Users, roles and teams · Workflow and approvals · Forms and rules ·
                         Competencies · Integrations and data I/O · AI governance · Security and audit
Header                   project switcher · Ctrl+K search · notifications bell · sync status chip · user
My Work                  approvals inbox and tasks
```

Rules: a module adds one entry to an existing group and never a top-level group; engines such as forms, rules and
eligibility are invisible to field users; offline sync is a status chip, not a page; comments are a drawer on any record.
Operator pages are not in this menu: they live under `/platform/*` on the operator origin (ADR 0017, OPS-12).

## Where every module surfaces

| Domain group | Module | Menu location |
|---|---|---|
| Platform and foundations | `arch` | Not in the menu |
| Platform and foundations | `database` | Not in the menu |
| Platform and foundations | `design` | App shell: header, rail, scope bar |
| Platform and foundations | `ops` | Settings > Operations (operator console, OPS-12) |
| Platform and foundations | `ref_packs` | Settings > Starter packs |
| Platform and foundations | `security` | Settings > Security and audit |
| Platform and foundations | `stack` | Not in the menu |
| Platform and foundations | `tenancy` | Settings > Organisation; billing at /settings/billing; operator pages under /platform |
| Platform and foundations | `terms` | Settings > Terminology |
| Platform and foundations | `testing` | Not in the menu |
| Identity and access | `access` | Settings > Users, roles and teams |
| Identity and access | `identity` | Settings > Users, roles and teams |
| Identity and access | `portal` | Settings > Portal users; external portal on its own origin |
| Asset and work core | `assets` | Work and assets > Assets |
| Asset and work core | `commissioning` | Work and assets (later phase) |
| Asset and work core | `components` | Tab or drawer inside Assets |
| Asset and work core | `item_types` | Work and assets > Item types |
| Asset and work core | `prefab` | Work and assets (later phase) |
| Asset and work core | `projects` | Scope bar project switcher; Settings > Organisation and projects |
| Asset and work core | `scope_work` | Work and assets > Scopes of work |
| Asset and work core | `service` | Work and assets (later phase) |
| Quality, inspection and HSE | `eligibility` | Settings > Competencies; also a server-side hard-block |
| Quality, inspection and HSE | `forms` | Settings > Forms and rules |
| Quality, inspection and HSE | `inspections` | Quality and compliance > Inspections and ITPs |
| Quality, inspection and HSE | `issues` | Quality and compliance > Issues, NCRs and CAPA |
| Quality, inspection and HSE | `punchlist` | Quality and compliance > Punch list |
| Quality, inspection and HSE | `qms` | Quality and compliance > Quality roll-up |
| Quality, inspection and HSE | `rules` | Settings > Forms and rules |
| Quality, inspection and HSE | `safety` | Quality and compliance (HSE) |
| Quality, inspection and HSE | `temporary_works` | Quality and compliance (register) |
| Field, logistics and resources | `diary` | Field and execution > Site diary |
| Field, logistics and resources | `equipment` | Field and execution > Plant, materials and consumables (tab) |
| Field, logistics and resources | `inventory` | Field and execution > Plant, materials and consumables (tab) |
| Field, logistics and resources | `logistics` | Field and execution (later phase) |
| Field, logistics and resources | `offline` | Header sync status chip |
| Field, logistics and resources | `resources` | Field and execution > Schedule and resources |
| Field, logistics and resources | `schedule` | Field and execution > Schedule and look-ahead |
| Field, logistics and resources | `voice_phone` | Capture widget inside Site diary |
| Records, collaboration and intelligence | `ai_assistant` | Insight > AI assistant; drawer anywhere |
| Records, collaboration and intelligence | `ai_gov` | Settings > AI governance |
| Records, collaboration and intelligence | `approvals` | My Work inbox; Settings > Workflow and approvals |
| Records, collaboration and intelligence | `audit` | Settings > Security and audit; History tab on records |
| Records, collaboration and intelligence | `change` | Documents and transmittals (later phase) |
| Records, collaboration and intelligence | `comments` | Right-hand activity drawer; header notifications bell |
| Records, collaboration and intelligence | `contacts` | Settings > Organisation (shared contacts and companies) |
| Records, collaboration and intelligence | `data_io` | Settings > Integrations and data I/O |
| Records, collaboration and intelligence | `documents` | Documents and transmittals > Documents |
| Records, collaboration and intelligence | `handover` | Documents and transmittals > Handover packs |
| Records, collaboration and intelligence | `ingestion` | Settings > Integrations and data I/O |
| Records, collaboration and intelligence | `integrations` | Settings > Integrations and data I/O |
| Records, collaboration and intelligence | `interfaces` | Documents and transmittals (later phase) |
| Records, collaboration and intelligence | `markup` | Viewer overlay inside Documents and Inspections |
| Records, collaboration and intelligence | `meetings` | Insight (later phase) |
| Records, collaboration and intelligence | `procurement` | Documents and transmittals (later phase) |
| Records, collaboration and intelligence | `report_engine` | Insight > Dashboards and reports |
| Records, collaboration and intelligence | `reporting` | Insight > Dashboards and reports |
| Records, collaboration and intelligence | `rfi_submittals` | Documents and transmittals > RFIs and submittals |
| Records, collaboration and intelligence | `search` | Header Ctrl+K; Insight > Search |
| Records, collaboration and intelligence | `signing` | Inside Documents and Inspections; never a menu item |
| Records, collaboration and intelligence | `tasks` | My Work |
| Records, collaboration and intelligence | `transmittals` | Documents and transmittals > Transmittals |
| Records, collaboration and intelligence | `uploads` | Shared upload control |
