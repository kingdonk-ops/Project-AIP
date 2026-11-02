# ADR 0027: How the access matrix levels become permission codes

- **Status:** accepted (owner, 2026-10-13: Client Reviewer "approve" is read plus sign-off only)
- **Date:** 2026-10-13
- **Affects:** access (ACCESS-02 seed, ACCESS-05 matrix page), every module that declares permissions

## Context

ACCESS-02 seeds the 11 tenant roles from `docs/blueprint/05-access-matrix.md`, which gives each role a level
(`none`, `view`, `create`, `edit`, `approve`, `admin`) per module. The catalogue holds concrete codes declared by the
module manifests, and their last segment (the verb) is not uniform: `project.view`, `project.archive`,
`access.role.read`, `site.manage`. The task says levels expand cumulatively by verb, but it names only some verbs.
The owner's Client Reviewer note (2026-10-10) also says that role is read-only plus sign-off, with no `create` or
edit anywhere, which a strictly cumulative `approve` level would break.

## Decision

1. A permission's verb is the last dot-separated segment of its code.
2. Levels add verbs cumulatively: `view` gives `read` and `view`; `create` adds `create`; `edit` adds `update`,
   `delete`, `edit` and `archive`; `approve` adds `approve` and `sign`; `admin` adds `manage` and `export`.
3. A verb that no level names is granted only at `admin` (fail closed). A module author who adds a new verb
   either uses one of the verbs above or accepts that only `admin` roles get it by default.
4. Client Reviewer's `approve` grants the `view` verbs plus `approve` and `sign`, not `create` or `edit`.
5. Matrix modules with no catalogue codes are skipped (logged once per seed). They are picked up automatically when
   their module declares permissions and the seed runs again (`aip-access seed-roles`, or tenant provisioning).

## Consequences

- New modules should name permissions with the verbs above so the default roles get them at the right level.
- Tenant admins can still change any role (ADR 0020); this only sets the shipped defaults and what `reset` restores.
- A customised role never gains new catalogue codes automatically; the seed reports them instead.

## Amendment (ACCESS-07, 2026-10-28): `move` at `edit`, `invite` at `approve`

Owner, 2026-10-18 (ADR 0036 §10, PORTAL-01):

- `edit` also adds `move`. Default roles that edit assets (`asset.update`) can now reorganise the tree
  (`asset.move`), while `asset.move` stays a separate code a tenant admin can withhold from any role.
- `approve` also adds `invite`. That is the level Project Manager holds on the portal module, so project admins get
  `portal.user.invite` and can invite portal clients; edit-level roles (QA/QC Manager, Document Controller) see
  portal users but cannot invite them.
- §4 is tightened to keep its intent: Client Reviewer's `approve` grants the `view` verbs plus only `approve` and
  `sign` (`SIGN_OFF_VERBS`), never `invite`.

Existing tenants pick the new codes up with `aip-access seed-roles`: uncustomised system roles are extended in place;
a customised role is left alone and its new codes are reported as pending (§5, ADR 0020).

## Amendment (2026-11-02): `respond` at `create`, and the quality hierarchy on Inspections

Owner, 2026-11-02:

- `create` also adds `respond`. `inspection.respond` (INSPECTIONS-02, answering inspection questions) fell under
  §3 and went to `admin` only, so by default only Tenant Admin could fill in an inspection. Every role at `create` or
  above on Inspections now answers them; Client Reviewer's `approve` still adds only `SIGN_OFF_VERBS` (§4).
- The Inspections row follows the quality hierarchy: the QA/QC Manager (lead inspector) creates, changes and manages
  ITPs, so it moves to `admin` (`itp.manage`, and `itp.waive`, an unnamed verb that stays admin-only); the Inspector
  signs ITP steps, so it moves to `approve` (`itp.sign`); the Supervisor (a trade lead, e.g. painting or mechanical)
  ranks below the inspector, so it moves to `create` (create and answer inspections, no sign-off). Project Manager
  stays at `approve`. Other modules keep their levels.

Existing tenants pick the new codes up with `aip-access seed-roles` (§5). A system role that loses codes
(Supervisor's `approve`-level Inspections codes) is changed only when it is uncustomised; a customised one is left
as the tenant admin set it.
