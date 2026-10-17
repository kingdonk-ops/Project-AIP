# QA-3 — Seed a kaefer-demo viewer; real-session server-403 journey for /projects/new

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`testing`](../../docs/blueprint/modules/testing/README.md) |
| Phase | P0 |
| Size | XS |
| Depends on | TESTING-09 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/testing/README.md`](../../docs/blueprint/modules/testing/README.md)
3. ADRs: none
4. [review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md), the finding named below

## Background

[review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md) finding **M12**. `e2e/web/projects.spec.ts:36-42` still has `test.skip(true, "needs IDENTITY-03 … ACCESS-02")`
although both are done. The denial test uses the dev stub, and no real-session user without `project.create` is seeded.
The MSW unit test for the 403 branch of `ProjectCreateForm.tsx` is a separate quick fix.

## Spec

The UI's handling of a server-enforced 403 on project create is proven with a real session.

- **files**:
  - identity/tenancy seeds
  - e2e/web/projects.spec.ts
  - e2e/playwright.config.ts
  - .github/workflows/ci.yml, deploy-coolify.yml (E2E_USER_VIEWER)
- **steps**:
  - 1. Seed a kaefer-demo viewer without `project.create`.
  - 2. Add `E2E_USER_VIEWER` (owner adds the demo secret).
  - 3. Turn the skip into a real `@skeleton` test: the viewer submits `/projects/new` and sees the server-denied message.
  - 4. Delete the stale admin-journey skip.
- **acceptance**:
  - The viewer journey runs in `e2e-skeleton` and is green.
  - No stale skip remains in `projects.spec.ts`.
- **tests**:
  - **e2e**:
    - viewer signs in, posts the create form → 403 surfaced as the permission message; no project created
