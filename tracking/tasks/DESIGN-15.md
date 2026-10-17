# DESIGN-15 — Nav items honour release flags, and a Settings page to switch them

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | ARCH-08, DESIGN-06 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/design/README.md`](../../docs/blueprint/modules/design/README.md)
3. ADRs: 0018
4. [review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md), the finding named below

## Background

[review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md) finding **L26**. Feature flags have no web consumer: nav items can't be flag-gated and there is no
flags admin page. ARCH-08 left this to "the web shell task", which doesn't exist.

## Spec

The web shell hides flag-gated nav items and admins can switch release flags.

- **files**:
  - apps/web/src/shell/nav-registry.ts
  - apps/web/src/routes/_app/settings/ (flags page)
  - e2e/web/
- **steps**:
  - 1. Let `registerNavItem` take an optional flag; read `GET /settings/flags` once per session.
  - 2. Add a Settings page listing flags with switches, behind `tenant.flags.manage`, calling `PUT /settings/flags/{flag}`.
- **acceptance**:
  - A nav item with a disabled flag is not shown.
  - An admin can switch a flag; a user without the permission cannot see the page.
- **tests**:
  - **unit**:
    - nav item with flag off → not rendered
  - **e2e**:
    - admin switches `bim` on → the gated item appears; cross-tenant: tenant B's flag unchanged; axe clean
