# ACCESS-08 — Policy cache hardening: expiry-bounded entries, deactivation bump, team delegation guard

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`access`](../../docs/blueprint/modules/access/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | ACCESS-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/access/README.md`](../../docs/blueprint/modules/access/README.md)
3. [`ACCESS-04.md`](ACCESS-04.md) (the policy cache and teams this hardens)

## Spec

Close the gaps the ACCESS-04 review (PR #163, 2026-10-29) found where a revoked grant can outlive its end by up to the
5-minute cache TTL, and tighten project-level team delegation (tag: harden).

- **files**:
  - apps/api/aip/modules/access/roles/repository.py (`active_grants`)
  - apps/api/aip/modules/access/roles/grant_provider.py
  - apps/api/aip/modules/access/policy_cache.py
  - apps/api/aip/modules/access/teams/service.py
  - apps/api/aip/modules/access/tests/
- **steps**:
  - 1. Time-boxed assignments: `active_grants` also returns the earliest future `valid_from` / `valid_to` among the
    user's assignments; the cache entry's TTL is `min(CACHE_TTL_S, seconds until that boundary)` (skip caching when
    the boundary is under a second away).
  - 2. Deactivation: until IDENTITY-05 publishes `user.deactivated`, have identity's deactivate path invalidate the
    user's cached grants through a published access call (or confirm `principal.active` already refuses every
    request of a deactivated user, and record that here).
  - 3. Team delegation (owner decision needed): a non-tenant-admin managing a project-level team may only add members
    (including themselves) when they hold every permission of the team's live roles at the team's scope.
  - 4. Return the same 404 for "team not found" and "no permission to manage it" so team ids cannot be probed.
- **acceptance**:
  - A grant whose assignment's `valid_to` passes is refused on the next request after that instant, not up to 5 minutes later.
  - A project-level team manager cannot gain a role they do not already cover by adding themselves to a team.
- **tests**:
  - **unit**:
    - TTL for a cached entry with `valid_to` 30 s ahead is at most 30 s.
  - **integration**:
    - Assignment with `valid_to` = now + 2 s: `can()` true, then false after 2 s with Redis caching on.
    - Project team manager without `qaqc_manager` permissions adds self to a team holding `qaqc_manager` → 403.
    - Unauthorised GET of an existing team id and of a random id return the same 404.
  - **e2e**:
    - none (no user-facing page).
