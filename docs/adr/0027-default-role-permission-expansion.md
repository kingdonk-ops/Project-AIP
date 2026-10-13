# ADR 0027: How the access matrix levels become permission codes

- **Status:** proposed (ACCESS-02, 2026-10-13; awaiting owner confirmation)
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
