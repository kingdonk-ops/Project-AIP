# PLAN-R1 — Generate R1 task files just in time (ADR 0007; process in docs/reviews/07-delivery.md)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`arch`](../../docs/blueprint/modules/arch/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ACCESS-02, APPROVALS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/arch/README.md`](../../docs/blueprint/modules/arch/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope; this task's mandate), [0001](../../docs/adr/0001-typescript-greenfield-rebuild.md) (name translation table), [0002](../../docs/adr/0002-data-access-and-migrations.md), [0004](../../docs/adr/0004-repository-layout.md). Skim the rest for decisions that touch R1 modules.
4. [`docs/reviews/07-delivery.md`](../../docs/reviews/07-delivery.md): the section "Just-in-time task generation process for later phases" (the process to follow) and the "Moved out of P0" row of "P0 execution waves"
5. Per R1 module, when you generate its tasks: `docs/blueprint/modules/<m>/README.md` and `data-model.md` only. **Never** use `docs/blueprint/04-code-layout.md` (AIP-era), and never copy `architecture.md` paths verbatim, because they are Python. Translate them with the ADR 0001 table.

## Spec

Turn ADR 0007's R1 "Kaefer live" scope into board rows and agent-ready task files using the just-in-time process. Re-home the tasks parked in "Moved out of P0", and add a mechanical task linter so every generated task follows the ADRs (tag: extend).

R1 scope (ADR 0007 §4). Module folders and ID prefixes are below. IDs must match `tools/next_task.py`'s `TASK_ID` regex, so they **cannot contain underscores**.

| Module folder | ID prefix | R1 slice (from ADR 0007) |
|---|---|---|
| `assets` | `ASSETS` | asset tree (ltree) and register |
| `item_types` | `ITEMTYPES` | item types and per-type attribute schema |
| `forms` | `FORMS` | operator-authored JSON templates, revisions, renderer, append-only responses (no designer) |
| `inspections` | `INSPECTIONS` | inspections and ITPs on the APPROVALS-05 preset, hold points, sign-off, register |
| `eligibility` | `ELIGIBILITY` | certificate records and hard-block check |
| `scope_work` | `SCOPEWORK` | RSW, tasks, completion gate |
| `issues` | `ISSUES` | NCR basics (raise from a failed answer, lifecycle on the approvals engine) |
| `report_engine` | `REPORTS` | Gotenberg PDF from data templates, job, stored as an uploads `stored_files` row |
| `data_io` | `DATAIO` | AIP data migration, reconciliation report, dry-run |

- **files**:
  - tracking/BOARD.md
  - tracking/tasks/<PREFIX>-NN.md (one per R1 board row)
  - tracking/tasks/PLAN-P2.md (stub)
  - tracking/tasks/DATABASE-03.md, TENANCY-04.md, TESTING-06.md, TESTING-07.md, TERMS-04.md, TERMS-06.md (re-scope notes only)
  - tracking/OPEN-QUESTIONS.md
  - docs/adr/0009-r1-module-decisions.md (from `docs/adr/0000-template.md`)
  - tools/lint-tasks.ts
  - tools/lint-tasks.spec.ts
  - package.json (root script `lint:tasks`) and the ARCH-03 CI workflow (one step)
- **steps**:
  - 1. **Preconditions.** Read ADR 0007's status. If the owner has not confirmed the cut, still generate the tasks, but title the new board section "R1 (pending owner confirmation of ADR 0007)", and leave every R1 row `todo` with deps that cannot be met before P0-core exit (step 6).
  - 2. **Gate before generation** (process step 2). For each R1 module, copy its README "Open questions" into `tracking/OPEN-QUESTIONS.md` under a new heading "R1 gate". Record every question the owner has already answered as one line in ADR 0009 (`- <module>: <decision> (answered <date>)`). Record the questions settled by P0 work as decided, citing the task. Example: inspections "XState vs workflow table" → the approvals engine (APPROVALS-01/05). A task that depends on an unanswered question gets status `blocked` and a note `waits on OPEN-QUESTIONS #N`. Do not guess the answer.
  - 3. **Generator inputs.**
    - The README, `data-model.md` and ADRs of each module.
    - `git ls-files apps packages db config` for the real tree.
    - The published interfaces of merged modules (`apps/api/src/modules/*/api.ts`, `manifest.json`), especially approvals, uploads, access, projects, audit and terms.

    Cite real exported names and paths, e.g. `ApprovalsApi.startInstance`, `UploadsApi.createSession`, `registerGuardContextProvider`. Do not cite blueprint names.
  - 4. **Pass A (slice plan).** For each R1 module, add 4–8 board rows: first the minimum that unblocks dependent modules, then accepted features. Each row has size ≤ M and deps on real IDs.
    - Ordering hint: assets and item_types first, then forms, then inspections, then eligibility and scope_work, then issues and report_engine. data_io comes last, because it maps onto the final schemas.
    - Rows that aren't Pass B get a stub file. The stub has the template header table, a one-sentence goal, and the line `Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).`
  - 5. **Pass B (full specs).** For the **first 3** rows of each module, write full task files from `tracking/tasks/_TEMPLATE.md`, keeping the `hand-written` marker. Match the detail of `ARCH-01.md` and `APPROVALS-02.md`:
    - concrete files under `apps/`, `packages/`, `db/migrations/<timestamp>_<name>.sql`, `config/`, `e2e/`
    - numbered steps
    - observable acceptance
    - unit, integration and e2e tests with concrete inputs and expected results (Vitest, Testcontainers-node, Playwright)
    - a tag of extend, harden or port (port only when the AIP source is cited and available)
    - rules and guards in JSONLogic
    - files through the uploads pipeline
    - PDF through report_engine jobs
  - 6. **Board.** Add a section `## R1 Kaefer live (ADR 0007)` after the P0 waves. It has wave tables in the same 7-column format, waves of at most 8 parallel tasks, and the critical path (assets → forms → inspections → report_engine) first. R1 rows depend on the P0 tasks they consume (e.g. INSPECTIONS-01 on APPROVALS-05 and FORMS-0x).
  - 7. **Re-home "Moved out of P0"** (ADR 0007 §3, 07-delivery "Moved out of P0"). Every row must stay parseable, and none may become ready by accident:
    - `DATABASE-03` → replaced by a `DATAIO-0x` "AIP migration and reconciliation" row. DATABASE-03 becomes `dropped`, with the note `replaced by DATAIO-0x`.
    - `TERMS-06` → re-scoped into data_io (aliases for import). Rewrite its spec to TS paths per ADR 0001, depend it on the DATAIO import row, and move the row into the R1 section.
    - `TESTING-06` → split. The hold-point and completion-gate scenarios become rows in INSPECTIONS and SCOPEWORK, and the golden report becomes a REPORTS row. TESTING-06 becomes `dropped`, with the note `split into <IDs>`.
    - `TENANCY-04` and `TESTING-07` → P2. Move them into a new section `## Later (P2+)` and add `PLAN-P2` to their deps.
    - `TERMS-04` → P4. Move it to the same section with status `blocked` and the note `deferred to P4 (ADR 0007)`.
    - `PLAN-P2` is a new stub row and file (module `arch`, size M). Its goal: "generate P2 task files once R1 passes its midpoint". It depends on the R1 row you mark as the midpoint.
    - The "P0-hardening" rows keep `PLAN-R1` as their only gate. That is intended.
  - 8. **Mechanical lint** (`tools/lint-tasks.ts`, run with `pnpm lint:tasks`, TypeScript only). It checks every `tracking/tasks/*.md` file that has status `todo` or `in-progress` on the board.
    - (a) File paths are only under `apps/ packages/ db/ config/ infra/ e2e/ tests/ tools/ tracking/ docs/`. It rejects `backend/`, `frontend/`, `.py`, `alembic`, `arq`, `celery`, `pytest` and `migrations/versions/`.
    - (b) There is at most one `db/migrations/` path, and it matches `db/migrations/<timestamp>_<name>.sql` (literal `<timestamp>` or 14 digits). It is never numbered like `0100_`.
    - (c) Size is XS, S or M.
    - (d) Every dependency ID exists on the board.
    - (e) Module code paths come from exactly one module (`apps/api/src/modules/<m>`, plus that module's `apps/web/src/features/<m>` or `apps/field`/`apps/worker` processors).
    - (f) A `tag: extend|harden|port` is present, and `port` only appears with an AIP citation.
    - (g) Tables named in tests appear in a merged migration or in the files or steps of the task or one of its deps.
    - (h) The header has the template table and the `hand-written` marker.

    Add the CI step. Existing P0 files that still say "rewrite per ADR 0001" are reported as warnings, not errors.
  - 9. **Validate** with `pnpm lint:tasks` (0 errors on generated files) and the existing board checker `tools/next_task.py --check` (0 errors). Then do the phase-entry review (process step 5): open the PR with the R1 wave table at the top of its description, and leave PLAN-R1 in `review` until a human or lead agent approves it.
- **acceptance**:
  - Every R1 module in the table has 4–8 board rows. Its first 3 have full specs, and the rest have stubs.
  - No generated file references `04-code-layout.md`, Python, Alembic, arq, Celery, `backend/` or `frontend/`.
  - `pnpm lint:tasks` and `next_task.py --check` both report 0 errors.
  - The six "Moved out of P0" tasks are re-homed as in step 7, and none of them becomes ready when PLAN-R1 is marked done, except TERMS-06 once its DATAIO dependency is done.
  - Each R1 module's open questions are recorded as ADR 0009 lines or OPEN-QUESTIONS entries, and dependent tasks are `blocked` where unanswered.
  - Rolling horizon: no P2 task files exist other than the `PLAN-P2` stub and the rows moved in step 7.
- **tests**:
  - **unit**:
    - These run `tools/lint-tasks.spec.ts` with Vitest on fixture markdown files:
      - A task listing `backend/app/modules/x/service.py` → error `forbidden path: backend/`.
      - Two `db/migrations/` paths → error `more than one migration`.
      - `migrations/versions/0100_x.sql` → error `numbered or non-db migration path`.
      - Size `L` → error `size must be XS, S or M`.
      - Dep `FOO-99` not on the board → error `unknown dependency FOO-99`.
      - No tag → error `missing extend/harden/port tag`.
      - `tag: port` without an AIP citation → error `port tag needs an AIP source citation`.
      - The valid fixture (copy of `APPROVALS-02.md`) → 0 errors.
  - **integration**:
    - `pnpm lint:tasks` on the repo → exit 0, and `0 errors` printed for the generated files.
    - `python3 tools/next_task.py --check` → `N tasks checked, 0 errors`.
    - In a temporary copy of the repo, set every P0 row except the "Later (P2+)" and hardening rows to `done`, then run `next_task.py --all`. Expected:
      - The first R1 wave appears (ASSETS-01, ITEMTYPES-01, …) along with the P0-hardening rows.
      - TENANCY-04, TESTING-07 and TERMS-04 are absent.
      - DATABASE-03 and TESTING-06 show as `dropped`.
  - **e2e**:
    - Agent dry run: take the first ready R1 task from `next_task.py` and resolve every relative link in its "Read before starting" list and spec → all targets exist. Every path in its **files** list that the task does not itself create already exists in the repo.
