# ADR 0018: Domain groups and navigation by job area; modules stay separate

- **Status:** proposed: **owner to confirm**
- **Date:** 2026-10-10
- **Affects:** design (nav rail), every module's UI entry, docs only for the code layout

## Context

62 active modules (`cost_items` and `cases` stay removed) are too many for a navigation menu, and too many to
reason about as a flat list. A review proposed six domain groups, a job-area menu with supporting modules
demoted into settings, drawers and utility bars, and several module merges.

## Decision

1. **Adopt six domain groups** (Platform and foundations; Identity and access; Asset and work core; Quality,
   inspection and HSE; Field, logistics and resources; Records, collaboration and intelligence) as an ownership and
   documentation overlay. The mapping is in [`docs/architecture/module-groups-and-navigation.md`](../architecture/module-groups-and-navigation.md).
   It changes no code layout, module names or import-linter contracts.
2. **Adopt the job-area menu.** Top level: Work and assets; Quality and compliance; Field and execution; Documents
   and transmittals; Insight; Settings (permission-gated). Supporting modules (forms, rules, eligibility, approvals
   configuration, integrations, AI governance, audit) live under Settings; markup, signing, components, comments and
   voice/phone are embedded in their parent surface; offline sync is a header status chip; notifications and global
   search are header utilities. A module adds one entry to an existing group; it never adds a top-level group.
3. **No module merges now.** Each proposed merge was checked against the build order and task dependencies:

   | Proposed merge | Decision | Reason | Revisit when |
   |---|---|---|---|
   | identity + access | keep | `access` is a platform layer plus a small catalogue module; identity does not import it | import-linter reports a cycle |
   | forms + rules | keep | `rules` also feeds approvals and eligibility; merging breaks that shared use | a shared evaluator is moved to `aip/platform` |
   | documents + markup + signing | keep | `signing` backs inspection sign-off (ADR 0010) and must not depend on documents | never for signing; markup may fold into documents |
   | reporting + report_engine | keep | report_engine renders published records (R1, ADR 0007); reporting is dashboards (P3) | both are built |
   | inventory + equipment | keep | both stay in P1: equipment calibration drives the certificate hard-block, inventory batches drive weld traceability | UI only: one nav entry with tabs |
   | approvals + rules into platform | keep | `approvals` is already P0 | none |

4. **Build order unchanged.** The proposed order matches ADR 0007 and `06-build-order.md` except that equipment and
   inventory stay in P1 (3 above) and handover, contacts, ingestion and ref_packs, which the proposal omitted, keep
   their existing phases.
5. `cost_items` and `cases` remain removed (`REMOVED` in `tools/split_blueprint.py`; hard rule in the agent rules).

## Consequences

Documentation and navigation only. DESIGN tasks and each module's UI task follow the group table when they add a
nav entry. Merges can be proposed again with evidence from the revisit column.
