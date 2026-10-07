# PROJECTS-02 — Projects register page + create form (M0 UI slice)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`projects`](../../docs/blueprint/modules/projects/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DESIGN-02, PROJECTS-01, STACK-03 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/projects/README.md`](../../docs/blueprint/modules/projects/README.md)
3. ADRs: 0004 (apps/web Next.js App Router, packages/ui, packages/api-client), 0005 (cookie session, no JWT in the browser), 0007 (M0 step 9)
4. Only if the step needs it: the `/projects` and `/projects/new` sections of [`routes.md`](../../docs/blueprint/modules/projects/routes.md)

## Spec

Give a signed-in user a Projects register and a create form inside the app shell, using only the generated API client and terminology keys. This is the visible M0 slice.

- **files**:
  - apps/web/src/features/projects/ProjectsRegister.tsx
  - apps/web/src/features/projects/ProjectCreateForm.tsx
  - apps/web/src/features/projects/columns.ts
  - apps/web/src/features/projects/nav.ts
  - apps/web/src/features/projects/__tests__/
  - apps/web/src/app/(app)/projects/page.tsx
  - apps/web/src/app/(app)/projects/new/page.tsx
  - config/terms/en-AU/projects.json
- **steps**:
  - 1. Add the term keys to `config/terms/en-AU/projects.json` (for example `projects.register.title` = "Projects", `projects.field.code` = "Project code", `projects.status.draft` = "Draft", `projects.empty.title`, `projects.create.submit`, `projects.error.code_taken`). Every visible string goes through the `t()` that DESIGN-02 provides. TERMS-01/02 later replace the source without changing call sites.
  - 2. Build the register at `/projects` with these columns: code (IBM Plex Mono), name, site, region, status (StatusChip: icon plus label) and updated. Data comes from the generated list hook in `packages/api-client`, using server-side cursor pagination, status filter and `q` search. Keep filter state in the URL query string. Use DESIGN-03's `RegisterTable` if it is merged. Otherwise use the `packages/ui` Table primitives with the same column definitions in columns.ts, so switching later is a one-line change. Do not write a new table component.
  - 3. Add the empty, loading and error states. The empty state has a Create project action shown only when the user has `project.create`. The error state shows the request correlation id.
  - 4. Build the create form at `/projects/new` with react-hook-form, validated by the Zod schema generated from the API (not a hand-copied schema). Fields: code, name, site (select from the sites list hook, optional), region, timezone (default: the browser's IANA zone if it is valid) and currency (default AUD). On 201, redirect to `/projects?created=<code>`. On 409 `PROJECT_CODE_TAKEN`, put the error on the code field. On 422, map each field path onto its input.
  - 5. Register the "Projects" nav item (icon plus term key) in the shell's nav config through `nav.ts`. Show it only when the principal has `project.view`. Hide the Create button without `project.create`. The server still enforces both.
  - 6. Make every input reachable by its label, give buttons accessible names and support keyboard-only creation. axe must report no serious or critical violations on both pages.
  - 7. Make no direct `fetch` and hold no token in the browser. All calls go through the generated client to `/api/v1/*` on the same origin, with the session cookie.
- **acceptance**:
  - A signed-in user with `project.view` sees only their tenant's projects at `/projects`, with working status filter, search and next/previous pages.
  - A user with `project.create` can create a project and sees it in the register without a manual reload.
  - A duplicate code shows an inline field error and keeps the user's input.
  - The terminology lint (if merged) and an `rg` check for hard-coded JSX text in `features/projects` find nothing.
  - `pnpm --filter web build` passes with 0 type errors against the current `packages/api-client`.
- **tests**:
  - **unit** (Vitest + Testing Library, with the client mocked through MSW):
    - Rendering the register with 2 items `[{code:'L592', status:'active'}, {code:'KIPS-01', status:'draft'}]` shows 2 rows. The status cells read "Active" and "Draft", each with an icon.
    - With an empty list and `project.create` granted, the empty state shows "Create project". Without the permission it does not.
    - Submitting the form with code `'ab cd'` shows the code validation message and sends no request.
    - When the server answers 409 `PROJECT_CODE_TAKEN`, the code field shows the `projects.error.code_taken` text and the name field keeps its value.
    - vitest-axe on the register and the form returns no violations.
  - **integration**:
    - Run the web app against the compose API with seeded tenants. Select status=active. Expected: the URL contains `status=active`, and reloading the page restores the same filter and rows.
    - Seed 60 projects and click Next. Expected: rows 51–60 load in a single list request with the cursor from page 1.
  - **e2e** (Playwright, project `web`):
    - Log in as the kaefer-demo admin, open Projects, click Create project, enter code `E2E-<run>` and name `Walking skeleton`, then submit. Expected: the URL is `/projects?created=E2E-<run>`, and the row appears with status Draft.
    - Log in as a kaefer-demo user without `project.create`. Expected: no Create button, and visiting `/projects/new` directly shows the permission-denied state (the server answers 403).
