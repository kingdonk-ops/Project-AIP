# ADR 0039: Owner answers on item-type inheritance, schema changes, starter packs, witness notification and root-cause method

- **Status:** accepted
- **Date:** 2026-10-30
- **Affects:** item_types (inheritance after R1, ITEMTYPES-06), inspections (INSPECTIONS-03, PORTAL-06), issues (ISSUES-06)

## Context

[OPEN-QUESTIONS.md](../../tracking/OPEN-QUESTIONS.md) "R1 gate" lists the questions PLAN-R1 copied from the R1 module
READMEs ([ADR 0036](0036-r1-module-decisions.md)). On 2026-10-30 the owner answered #38, #39, #41, #43 and #46.
#40, #44 and #47 to #49 stay open.

## Decision

### #38 Item-type inheritance: bounded overrides, tighten only

A child item type (`item_types.parent_type_id`) inherits every attribute of its parent. The rule is that **an asset of
a child type must still be valid as an asset of the parent type**, so reports, rules and templates written against the
parent keep working for every child.

| A child type may | Rule |
|---|---|
| Add attributes | Always |
| Make an optional attribute required | Tighten only; never required → optional |
| Narrow the tolerance (min/max/target) | Must stay inside the parent's range |
| Change the unit | Same dimension only (mm ↔ in), converted |
| Restrict dropdown options | A subset of the parent's options |
| Change label, help text, default value or order | Display only, always allowed |

A child type may **not** remove an inherited attribute, loosen any rule, or change an attribute's key or field type.
If a child needs to drop an attribute, the attribute belongs lower in the hierarchy: move it from the parent into the
children that need it, or make the child a sibling.

- Overrides live in the child version's `attribute_schema` (for example an `overrides` block keyed by attribute key);
  `inheritance.py` resolves the effective schema up the parent chain.
- Publishing a child version is refused unless every override tightens the parent's published rule.
- No cycles; at most 3 levels below a root type.
- The type editor shows own, inherited and overridden attributes, with the parent's value next to an override.

This extends the advisors' "add-only with overrides of required, unit and tolerance" with the tighten-only rule and safe
overrides for options and display fields.

### #39 Schema changes: pinned versions plus a migration preview

- Assets stay pinned to the item-type version they were created or last migrated on (`item_type_version_id`, already
  in R1 via ITEMTYPES-02 and ASSETS-02). Publishing a new version changes no existing asset.
- Completed inspections are never migrated; they keep the form revision and type version they were completed against.
- Moving assets to a newer version is an explicit admin step behind a migration preview with impact counts (assets
  affected, values that fail the new rules). A parent change that a child's override no longer tightens shows as a
  conflict in that preview, not as a silent failure.

### #41 Starter packs: three ways to start

A tenant can start in any of three ways, and mix them:

1. **Blank slate:** no packs; the tenant builds its own types.
2. **Provisioned for them:** the operator installs and tailors packs on the tenant's behalf (owner-curated per-tenant
   content, through the operator console of [ADR 0017](0017-company-systems-and-contract-link.md)).
3. **Self-selected:** the tenant admin picks industry-standard packs (NDT/CUI, welding, insulation, coating) shipped
   with the product as platform rows ([ADR 0028](0028-platform-tenant-rows.md)), previews and installs them.

Installed packs become ordinary tenant-owned types the tenant can edit; `starter_pack_installs` records what was
applied. This unblocks ITEMTYPES-06.

### #43 Witness notification: the system notifies in-system witnesses

- When a witness point is booked, the system notifies the **client inspector** (a portal user on the project) with the
  project's notice period (`witness_notice_hours`). The notification is recorded on the witness point, so it becomes a
  documented control rather than a QA phone call or email that leaves no record.
- A **third-party inspector** who is not a user in the system is not notified by it; QA notifies them outside the
  system as today.
- Other systems (ITPpro and others) notify witnesses too; this is parity plus an audit record, not a differentiator.

### #46 Root-cause method: both, tenant chooses the default

Both 5-why and fishbone are available. The tenant admin sets the default in settings, or is asked on first use (the
first time a root cause is recorded); the default can be changed later. This unblocks ISSUES-06.

## Consequences

- ITEMTYPES-06 and ISSUES-06 move from `blocked` to `todo`; their full specs follow these answers.
- Inheritance and the migration preview stay after R1 ([BACKLOG.md](../../tracking/BACKLOG.md)); when they are pulled
  in, their tasks follow #38 and #39 above.
- INSPECTIONS-03 and PORTAL-06 record the witness notification on the point; PROJECTS-04 already carries
  `witness_notice_hours`.
- The item_types, inspections and issues READMEs mark these questions answered.
