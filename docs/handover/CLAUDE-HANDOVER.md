# Handover: continue building Project-AIP as the coordinating agent

Give this file to a Claude session (Claude Code, cloud or local) running under the owner's company account, with the repository `kingdonk-ops/Project-AIP` attached. Read it fully, then follow **section 2** to start.

You are taking over from the previous coordinating agent. Do the job the way it did: keep the board accurate, build small, test first, keep CI green, merge your own PRs once CI is green, and keep the owner's usage low.

> Written 2026-10-08. The repository files are the source of truth. If this file disagrees with `AGENTS.md`, `tracking/BOARD.md` or an accepted ADR, trust those and fix this file in your next docs PR.

---

## 1. What this is

**Project-AIP** is a greenfield, multi-tenant SaaS for construction/industrial quality and inspection work (projects, inspections, hold and witness points, sign-off, documents, AI-assisted features). The first customer is the owner's client "Kaefer" (demo tenant `kaefer-demo`), later Rio Tinto sites.

- **Owner:** the user (initials **KK**). Product decisions are theirs. They review merged work in batches. They are cost-sensitive: prefer small, finished steps over exploration.
- **Build model:** AI coding agents build one small task per branch. A 2.5 MB product blueprint was split into small files so an agent reads only what its task needs. **Never read `docs/blueprint/` wholesale.**
- **Existing AIP product:** an older codebase called AIP exists. **Never read, copy or use its code, schema or data.** "Port from AIP" in a doc means: implement the behaviour the blueprint describes, proven by tests. This is a legal provenance rule (ADR 0001, `docs/security/provenance-log.md`).
- **Current milestone:** **M0 walking skeleton** (waves 0 to 5): two tenants, Keycloak sign-in, Vite web shell, Projects register, row-level-security isolation proven in CI, deployed to a Coolify demo with synthetic data only.

### Stack (decided; do not re-litigate)

| Area | Choice | Where decided |
|---|---|---|
| Backend | Python 3.12 (CI also runs 3.13), FastAPI, Pydantic v2 | ADR 0001 |
| Data access | SQLAlchemy 2 **Core** + asyncpg (no ORM), Alembic forward-only **raw-SQL** migrations | ADR 0002 |
| Database | Postgres 16 (pgvector image), **FORCE row-level security** on every tenant table | ADR 0002, 0012 |
| Jobs | **Procrastinate** (Postgres queue) and a Postgres outbox. *Not* arq/BullMQ/Celery (some old task text still says arq: translate with ADR 0001) | ADR 0003 |
| Frontends | Vite + React + TanStack Router, three apps (web, field PWA, portal); pnpm workspace | ADR 0004 |
| Sign-in | **Keycloak** for all staff (SSO, password, MFA). The backend issues its own `__Host-` sessions, field PINs, portal links, SCIM | ADR 0005 |
| Cache/queue-ish | Valkey (not Redis), RustFS (S3-compatible), Gotenberg (PDF) in compose | STACK-05 |
| OCR | Tesseract + pypdfium2 + pikepdf; AWS Textract optional | ADR 0009 |
| Deploy | M0 on **Coolify** (bytedock.io), synthetic data only; AWS staging from wave 7 | ADR 0007, task OPS-11 |
| Licences | **No paid licences.** Open source or AWS only. No GPL/AGPL/SSPL dependencies. Other free licences (MIT, BSD, Apache, MPL, LGPL used unmodified as a library) are fine | ADR 0009, 0011 (accepted by the owner) |

---

## 2. First 15 minutes: orient and check state

Run these from the repo root. They are cheap.

```bash
cat AGENTS.md                              # the loop and the hard rules (short)
python3 tools/next_task.py                 # next ready task + exactly which files to read
python3 tools/next_task.py --all           # all ready tasks (for parallel work)
python3 tools/next_task.py --check         # validates the board (expect: N tasks checked, 0 errors)
git fetch origin && git log --oneline -10 origin/main
```

Then on GitHub (use the GitHub MCP tools; there is no `gh` CLI in cloud sessions):

1. List open PRs. At handover one was open: **PR #23 (IDENTITY-01)**, waiting on CI. If it is still open, check its checks; fix any red check; merge it with **squash** once everything is green (section 6).
2. Read `tracking/OPEN-QUESTIONS.md` (owner decisions and what is waiting on them) and the tail of `tracking/PROGRESS.md` (the last log lines show what was just done).
3. Read `tracking/BOARD.md` to see waves, dependencies and statuses.

### Where things stood at handover (2026-10-08)

- **Merged to `main`:** PRs #1 to #22. Waves 0 and 1 are done except DESIGN-01. Wave 2/3 items done: DATABASE-02 (runtime roles, `with_tenant`, fail-closed RLS), STACK-03, OPS-01 (job tables). SECURITY-08 (security CI) and STACK-05 (compose stack) are done.
- **Open:** PR #23 **IDENTITY-01** (Keycloak realms as code, `login_directory`, OIDC login). All checks were green except Python 3.13, which I had just fixed (the 422 response description differed between Python versions; fixed by pinning the description in `identity/routes.py`). Re-check it.
- **DESIGN-01** is `blocked`. It needs to write `packages/ui/eslint.config.mjs`, which the Everything Claude Code plugin's `config-protection` hook used to block. The owner merged PR #21, which disables that hook (`ECC_DISABLED_HOOKS` in `.claude/settings.json`). It should now be unblocked: set it back to `todo`/`in-progress` and run it.
- **Started but abandoned (nothing pushed):** ARCH-05, OPS-02, DATABASE-04. Their agents died mid-work and only a board claim or a dependency edit existed. Treat them as fresh `todo`. OPS-02's title says "arq": build it on **Procrastinate** per ADR 0003.
- **Next ready tasks** (after IDENTITY-01 merges): run `next_task.py --all`. Expect TESTING-02, TESTING-01, TENANCY-01, TERMS-01, ARCH-05, DATABASE-04, OPS-02, DESIGN-01 and OPS-11 depending on dependencies.

---

## 3. Repository layout

```
AGENTS.md  CLAUDE.md  README.md      CLAUDE.md just points to AGENTS.md
Makefile                             make check = check-py + check-ts + check-docs + check-boundaries
pyproject.toml  uv.lock              uv workspace (Python). pnpm-workspace.yaml + pnpm-lock.yaml (TS)
apps/
  api/                               FastAPI app (package `aip`)
    aip/platform/...                 cross-cutting: db (engine, with_tenant, migrator), context, version, logging
    aip/modules/<module>/            business modules, each with manifest.toml, api.py (public surface), routes.py,
                                     service.py, repository.py, tables.py, schemas.py, tests/
    migrations/versions/             Alembic revisions (raw SQL; ONE head)
    tests/                           platform/arch/integration tests (arch tests enforce boundaries)
  web/  field/  portal/              Vite apps (web exists; others come later)
packages/
  api-client/                        generated typed client + openapi.json (drift-checked in CI)
  config-eslint/  ui/ ...            shared TS config and UI kit
db/
  bootstrap/00_cluster.sql           superuser-only: creates roles aip_owner, aip_app, aip_jobs, aip_readonly (ADR 0012)
  templates/tenant_table.sql.tpl     the template every tenant table uses (FORCE RLS, fail-closed policy)
  schema.snapshot.sql                committed normalised schema dump (CI checks it is up to date)
infra/                               docker-compose.yml, Keycloak realms, Dockerfiles, nginx
config/                              licence-policy.json, prod-strip-manifest.txt, terms/en-AU/*.json, vuln-exceptions.txt
e2e/                                 Playwright tests
tools/                               next_task.py, split_blueprint.py, ci/*, codegen/*, sbom.sh, keycloak_messages.py
tracking/
  BOARD.md                           single source of truth for task status, waves and dependencies
  PROGRESS.md                        newest-first log, one line per merged task (date · TASK · PR · outcome)
  OPEN-QUESTIONS.md                  decisions waiting on the owner; resolved decisions
  tasks/<ID>.md                      one spec per task (files, steps, acceptance, tests)
docs/
  adr/                               architecture decision records (index in README.md). Latest accepted wins
  blueprint/                         split product blueprint (read only what a task names)
  reviews/  security/  architecture/ specialist reviews, threat model, provenance log
.github/workflows/                   ci.yml (python 3.12/3.13, typescript, db, boundaries, api-client, e2e, licences, compose),
                                     security.yml (Trivy, pip-audit, pnpm audit, bandit, gitleaks, cosign), tracking.yml, release.yml
```

**Module boundaries are enforced by CI** (import-linter, manifest checks, ESLint): a module may import another module only through its `api.py`; `platform` never imports `modules`; apps never import apps. Each module has `manifest.toml` declaring what it uses.

---

## 4. The loop (one task per branch, one PR per task)

Follow `AGENTS.md`. In short:

1. `python3 tools/next_task.py` (or take the ID you are given). Never start a task whose dependencies are not `done`. **Dependencies on the board override those in task files.**
2. Claim it: in `tracking/BOARD.md` set status `in-progress` and put your branch name in Notes.
3. Read, in order: `tracking/tasks/<ID>.md`, `docs/blueprint/07-task-conventions.md` (definition of done), the ADR index, ADRs naming your task, then the module README. Only read deeper docs if a step needs them.
4. **Test first.** Turn the spec's `tests` block into failing tests, then code until green. Use real Postgres. Never mock the database.
5. Verify (section 5).
6. Update `tracking/BOARD.md` (`review` when the PR opens, `done` when it merges) and add one line to `tracking/PROGRESS.md` (date, task, PR, outcome). Add an ADR (`docs/adr/0000-template.md`) for any decision no ADR covers, and a new `todo` row plus task file (`tracking/tasks/_TEMPLATE.md`) for any work you discover. Do not silently widen a task.
7. Open the PR using `.github/pull_request_template.md` (mirror its sections), then merge per section 6.

### Hard rules (from `AGENTS.md`; non-negotiable)

- Every table: `tenant_id`, uuid primary key, timestamps, soft delete (except append-only tables), `FORCE ROW LEVEL SECURITY`. Create tables from `db/templates/tenant_table.sql.tpl` via `render_template`.
- Tenant context only through `with_tenant`. Only `aip.platform.db` creates engines or connections (an arch test enforces this; two documented probes are allowed exceptions).
- The app connects as `aip_app` (never owner or superuser; `create_app_engine` refuses those). Jobs connect as `aip_jobs`.
- No hard-coded user-facing labels: use terminology keys (`config/terms/en-AU/*.json`).
- Authorisation only through the policy service plus RLS, deny by default.
- Files only through the upload pipeline; AI calls only through the AI gateway.
- Never build the removed modules `cost_items` and `cases`.
- OpenConstructionERP (AGPL) is a feature reference only: copy no code.
- No secrets in the repo. No real customer data outside AWS staging/production.

### Shared test fixtures (use these names everywhere)

| Fixture | Tenant slug | Email domain | Keycloak IdP alias | Dev user |
|---|---|---|---|---|
| Tenant A (Kaefer demo) | `kaefer-demo` | `kaefer.test` | `kaefer-oidc` | `alice@kaefer.test` |
| Tenant B | `tenant-b` | `acme.test` | `acme-oidc` | `bob@acme.test` |

---

## 5. How to build and verify locally

Prerequisites in a cloud session: `uv`, `pnpm`, Node, and a local Postgres 16 (the repo's `.claude/hooks/session-start.sh` starts one). If not running, start the compose Postgres or install `postgresql-16 postgresql-16-pgvector`.

```bash
# test database used by the integration tests
export AIP_TEST_DATABASE_URL=postgresql://aip_test:aip_test@localhost:5432/aip_test

make check            # python (ruff, pyright, pytest), typescript, docs checks, boundaries
python3 tools/next_task.py --check
uv run --python 3.13 pytest apps/api/tests/test_openapi_export.py -q   # CI runs 3.12 and 3.13: check both when you touch API routes
```

Tests that need a database or Keycloak are skipped locally if the service is missing; they run in CI, so a green local run with many skips is not proof. Run the relevant integration tests when you can.

### Migrations (easy to get wrong)

```bash
uv run aip-db new add_widgets      # blank revision (filename YYYYMMDDHHMM_name.py)
uv run aip-db lint                 # forward-only, raw SQL, one head, contract comments, immutability
uv run aip-db migrate              # needs DATABASE_MIGRATOR_URL as aip_owner
uv run aip-db snapshot             # rewrites db/schema.snapshot.sql: COMMIT IT (CI fails if stale)
uv run aip-db check-schema         # migrated schema vs declared SQLAlchemy Core tables
```

- Exactly **one Alembic head**. If `main` gained a revision while you worked, set your revision's `down_revision` to the new head and give it a fresh, later id (rename the file, `Revision ID`, `Revises`, and any `# contract:` comment that quotes the id). Then regenerate the snapshot.
- Lint rules: no `DO` blocks outside the baseline; `SECURITY DEFINER`, `TRUNCATE` and similar need a `# contract:` comment explaining why.
- To regenerate the snapshot against a clean database: create an empty database, run `db/bootstrap/00_cluster.sql` as the Postgres superuser with `PGOPTIONS="-c aip.owner_password=<pw>"`, set `DATABASE_MIGRATOR_URL=postgresql://aip_owner:<pw>@localhost:5432/<db>`, run `aip-db migrate` then `aip-db snapshot`. CI does the same with throwaway credentials.
- Never edit an applied revision. Add a new one.

### Generated files must have no drift

If you change API routes or schemas, regenerate and commit the OpenAPI/client (`make generate-client`; CI has a drift check) and the module map if the manifest changes. Descriptions must be identical on Python 3.12 and 3.13 (give responses explicit `description` values; do not rely on `http.HTTPStatus` phrases).

---

## 6. Git, PRs and merging (the owner's policy)

- **Branch:** work on the branch your session is assigned. If none, use `claude/p<phase>-<module>-<short>`; one task per branch.
- **Commit messages:** `TASK-ID: what changed`, with the attribution trailers the session instructs. Use `git commit -m "..."`. Do not use `--no-verify` or `--no-edit`.
- **Never rewrite shared history:** merge `origin/main` into your branch (no rebase, no force-push). Resolve conflicts, regenerate generated files with the tools, then push.
- **Merge policy ("b"):** you (the coordinating agent) merge a PR **when CI is fully green and any review agent reports no blocking findings.** Use **squash** merge. The owner reviews merged work in batches afterwards. Never merge with red CI or an unresolved blocking finding.
- **Keep PRs small and current.** When another PR merges first, `BOARD.md`/`PROGRESS.md` usually conflict: keep `main`'s content plus your own task row/line (they are append/edit-by-row files), and check `next_task.py --check` afterwards.
- **After a push, subscribe to the PR** (`subscribe_pr_activity`) so CI results arrive as events. Do not poll or sleep. When a check fails: read the job logs (`get_job_logs`, large logs are saved to a file: grep it), reproduce locally, fix the cause, run the checks, push once. Never skip, disable or quarantine a test to get green. "Flake" is not a root cause.
- **Security review:** for anything touching auth, sessions, crypto, RLS, SQL, or external input, spawn a security-review agent on the diff before merging and fix blocking findings. Put non-blocking findings into the relevant future task file as "Carried forward" notes (this is how earlier reviews were handled).
- **Parallel work:** several tasks in the same wave can run on separate branches/worktrees. Before spawning agents, check they will not touch the same files or the same Alembic head. Give each agent one task, the exact files to read and these rules. Do not commit an agent's unfinished work.

---

## 7. Web testing (the coordinating agent owns it)

- Every task that adds or changes a user-facing page ships Playwright tests in `e2e/` for its main journey, one cross-tenant check (the other tenant sees nothing / gets 404) and an axe accessibility check. Projects: desktop Chromium, mobile Chrome, iPad WebKit. The field PWA also tests offline.
- E2E runs in CI on every PR and must be green before merge. Chromium is pre-installed in cloud sessions (`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`); do not run `playwright install`.
- After each deploy to the Coolify demo (OPS-11), run the suite against the live URL (`E2E_BASE_URL`). A failure becomes a `QA-<n>` `todo` task on the board and is reported to the owner.

---

## 8. Security and secrets (read carefully)

- **The Coolify API key was pasted into an earlier chat.** Never store, repeat, echo or commit it. The owner chose to keep it for now. **It must be rotated before any real customer data goes onto Coolify.** Remind the owner when OPS-11 reaches deployment. Never ask the owner to paste keys.
- Secrets live **only** in GitHub Actions secrets: `COOLIFY_TOKEN`, `COOLIFY_WEBHOOK`, and optionally `COSIGN_PRIVATE_KEY` + `COSIGN_PASSWORD` (CI signs with a throwaway key until the owner adds them).
- **Synthetic data only** on Coolify and in tests. Seeds refuse to run when `AIP_ENV=production`.
- gitleaks scans the full history of every branch. A reviewed false positive goes into `.gitleaksignore` with a reason (the fake dev `PREAUTH_COOKIE_KEY` is already listed). Never put a real-looking key in the repo; generate test keys at run time.
- Do not weaken your own guardrails: do not edit Claude settings or hooks, and do not merge changes that weaken them, unless the owner asks. If a hook blocks you, stop and report; do not route around it.
- Licence checks (`licences` CI job + `config/licence-policy.json`) must pass. Adding a dependency means checking its licence first; unknown or copyleft (GPL/AGPL/SSPL) is denied. Container OS packages are judged as aggregation (ADR 0011).

### Tooling quirks seen in this environment

- A fact-forcing "GateGuard" hook may ask you to state facts (the request, what the command does) before the first Bash command or edit; state them and retry the same call.
- A `block-no-verify` hook can false-positive on `git commit --no-edit`; use `git commit -m`.
- If a hook misfires, split the command into smaller ones. Do not bypass hooks.
- Cloud sessions have no `gh`; use the GitHub MCP tools. Outbound network is a proxy: if TLS or a host fails, read `/root/.ccr/README.md`.

---

## 9. Owner decisions already made (do not ask again)

- Python backend; never use AIP code. Postgres queue (Procrastinate). Vite for all frontends. Keycloak for all staff sign-in. Start on Coolify.
- No paid licences; open source or AWS only. ADR 0011 (licence details) **accepted**. Provenance log **initialled KK 2026-10-08**.
- Merge policy "b": the coordinating agent merges green PRs; the owner reviews in batches.
- Run multiple branches in parallel where safe. The coordinating agent writes, runs and monitors web tests.
- Keep the current Coolify key for now; rotate before real data.
- If usage runs out, continue where you left off and **collect questions for the owner's next chat** in `tracking/OPEN-QUESTIONS.md`.

### Still waiting on the owner (do not block on these; keep working)

Listed in `tracking/OPEN-QUESTIONS.md`. Key ones: confirm ADR 0013 (security scanners); optionally add cosign secrets; make the `boundaries` check required in GitHub branch protection on `main`; and the product questions needed before P0-core exit / R1 (per-tenant KMS key, MVP date, billable seat classes, AI provider, retention, field-tablet policy). Raise new questions by adding to that file and mentioning them in your summary.

---

## 10. How to work like the previous coordinating agent

1. **Finish before starting.** Merge what is built before opening new work. At most a few PRs in flight.
2. **Be frugal.** Read only the files a task names. Do not re-read the blueprint. Use short outputs; save big logs to files and grep them. Do not re-run the whole suite after tiny docs changes (run `next_task.py --check` and `make check-docs`).
3. **Keep the board true.** Status, notes (branch, PR number), and a PROGRESS line for every merged task. Fix the board when it drifts.
4. **Report plainly.** When you report to the owner: what merged, what is open, what is blocked and why, and any decision you need from them. No marketing language. If a step was skipped or a test failed, say so.
5. **Ask only for owner-level decisions** (product scope, money, legal, secrets). Everything else: pick the sensible default, note it, move on.
6. **Add carry-forwards instead of widening tasks.** Non-blocking review findings go to the owning future task file under "Carried forward from <TASK> (non-blocking)".
7. **Never invent state.** Check the board, git and GitHub before saying something is merged, green or done.

### Suggested order of work from here

1. Merge PR #23 (IDENTITY-01) once green. Mark it done (already done on its branch).
2. Unblock and finish **DESIGN-01**, then **TESTING-02**, **TESTING-01** (they protect tenant isolation), then **TENANCY-01**, **TERMS-01**, **ARCH-05**, **DATABASE-04**, **OPS-02**, then wave 4 as dependencies allow. Re-check with `next_task.py --all` each time.
3. **OPS-11** (Coolify demo) when its dependencies are done: this is where the Coolify key rotation reminder applies.
4. Keep M0 as the goal: two tenants, sign-in, web shell, Projects register, isolation proven, demo deployed and monitored.

When you finish a stretch of work, leave the repo so the next agent can continue: board and progress up to date, no half-pushed branches, open questions written down, and a short summary of state in your final message.
