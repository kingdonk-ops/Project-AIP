# Agent operating manual

This repo is built by AI coding agents, one small task at a time. The product blueprint is
2.5 MB, so **never read all of it**. It is split so you read only what your task needs.

## The loop (one task per branch)

1. **Pick a task**
   ```bash
   python3 tools/next_task.py          # next ready task + the exact files to read
   python3 tools/next_task.py --all    # every ready task (run at most two build streams at once)
   ```
   Or take the task ID you were given. Never start a task whose dependencies aren't `done`.
2. **Claim it.** In [`tracking/BOARD.md`](tracking/BOARD.md), set its status to `in-progress`
   and put your branch name in the notes column.
3. **Read only this, in order**
   1. `tracking/tasks/<ID>.md`: the task spec (files, steps, acceptance, tests)
   2. [`docs/blueprint/07-task-conventions.md`](docs/blueprint/07-task-conventions.md): definition of done
   3. [`docs/adr/README.md`](docs/adr/README.md): skim the index, then read ADRs naming your task or module
   4. `docs/blueprint/modules/<module>/README.md`: module overview
   5. *Only if a step needs it:* `architecture.md`, `data-model.md` or `routes.md` in that module
      folder, or a numbered reference file listed in [`docs/blueprint/INDEX.md`](docs/blueprint/INDEX.md)
4. **Build it test-first.** Turn the spec's `tests` block into failing tests, then code until green.
   Use real Postgres via Testcontainers. Never mock the database.
5. **Verify.** Run lint, typecheck, unit and integration tests, and `python3 tools/next_task.py --check`.
6. **Record progress**
   - `tracking/BOARD.md`: status → `review` when the PR opens, → `done` when it merges.
   - `tracking/PROGRESS.md`: add one log line (date, task, PR, one-sentence outcome).
   - If you made a decision no ADR covers, add an ADR (copy `docs/adr/0000-template.md`).
   - If you discovered work that isn't on the board, add a `todo` row and a task file
     (copy `tracking/tasks/_TEMPLATE.md`). Don't silently widen your own task.
7. **Open a PR** with the template. One task per PR. Branch: `p<phase>/<module>-<short-desc>` (or the session's
   assigned branch, one task at a time).
8. **Merge policy (owner, 2026-10-07):** the coordinating agent merges a PR once CI is green and a review agent
   reports no blocking findings. The owner reviews merged work in batches. Never merge with red CI or an
   unresolved blocking finding.

## When documents disagree

1. ADRs in `docs/adr/` (the latest accepted one wins)
2. Owner decisions: `docs/blueprint/01-decisions.md`
3. Task spec: `tracking/tasks/<ID>.md`
4. Module docs: `docs/blueprint/modules/<module>/*`
5. Advisor text: `docs/blueprint/02-advisor-summaries.md`, `advice-*.md`

**This repo is a greenfield build: Python backend (FastAPI), TypeScript frontends (Vite).** The old AIP
codebase is not used: don't look for it or ask for it. "Port from AIP" means *implement the behaviour the
blueprint describes*, proven by golden tests. If a doc mentions NestJS, Kysely, BullMQ, arq, Celery, Next.js,
`services/...`, `backend/...` or `frontend/...`, translate it with the table in ADR 0001.

## Web testing (owner, 2026-10-07: the coordinating agent writes, runs and monitors it)

- **Write:** every task that adds or changes a user-facing page ships Playwright tests in `e2e/` for its main journey,
  one cross-tenant check (the other tenant sees nothing / gets 404), and an axe accessibility check. Projects: desktop
  Chromium, mobile Chrome, iPad WebKit; the field PWA also runs offline (`context.setOffline`).
- **Gate:** e2e runs in CI on every PR and must be green before merge (merge policy above).
- **Monitor:** after each deploy to the Coolify demo (OPS-11), the coordinating agent runs the e2e suite against the live
  URL (`E2E_BASE_URL`). A failure becomes a `todo` fix task on the board (`QA-<n>`) and is reported to the owner.
  Never skip, disable or quarantine a failing test to get green.

## Shared test fixtures (use these names everywhere)

| Fixture | Tenant slug | Email domain | Keycloak IdP alias | Dev user |
|---|---|---|---|---|
| Tenant A (Kaefer demo) | `kaefer-demo` | `kaefer.test` | `kaefer-oidc` | `alice@kaefer.test` |
| Tenant B | `tenant-b` | `acme.test` | `acme-oidc` | `bob@acme.test` |

Specs that say `kaefer`, `acme`, `tenant-a` or `tenant_a` mean these two tenants. Test-only module: `widgets`,
event `widget.created` v1. Seeds refuse to run when `AIP_ENV=production`.

## Status values

`todo` · `in-progress` · `review` · `done` · `blocked` (say why in notes) · `dropped` (say why)

## Hard rules

- Every table has `tenant_id`, a uuid PK, timestamps, soft delete (except append-only tables) and `FORCE ROW LEVEL SECURITY`.
- No hard-coded user-facing labels. Use terminology keys.
- Authorisation goes only through the policy service plus RLS, denying by default.
- Files go only through the upload pipeline. AI calls go only through the AI gateway.
- Never build the removed modules `cost_items` and `cases`.
- No secrets in the repo. No real customer data outside AWS staging/production.
- OpenConstructionERP (AGPL) is a feature reference only. Copy no code from it.

## Regenerating the split blueprint

The 2.5 MB source blueprint isn't committed. When the owner issues a new version, run:
```bash
python3 tools/split_blueprint.py path/to/product-blueprint.md
```
This rewrites `docs/blueprint/` and the generated task files. It never touches `tracking/BOARD.md`,
`tracking/PROGRESS.md`, ADRs or reviews. When you edit a task file, add
`<!-- hand-edited: reason -->` under its title so regeneration keeps your version.
