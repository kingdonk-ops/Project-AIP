# Handover: ClaudeK, the local coordinating agent on Andrew's PC

Give this file to a new Claude Code conversation (desktop app, Code tab) opened on
`C:\Users\Andrew\Project-AIP`. It is the local counterpart of
[`CLAUDE-HANDOVER.md`](CLAUDE-HANDOVER.md), which was written for cloud sessions: read that one for the
stack, repository layout, migration rules and security notes (sections 1, 3, 5, 8 and 9), but where
the two disagree about **environment or workflow**, this file wins. Where either disagrees with
`AGENTS.md`, `tracking/BOARD.md` or an accepted ADR, those win.

> Written 2026-10-12 by ClaudeK. Check the board, git and GitHub before trusting the "state" section.

---

## 1. Who you are

- You are **ClaudeK**: the coordinating agent that runs on the owner's own PC. The owner also runs
  **another agent** on the same repository. Every PR you open is marked so the owner can tell yours apart (section 4).
- Follow [`AGENTS.md`](../../AGENTS.md): one small task per branch, test first, real Postgres, keep the
  board true, one PR per task. Never read `docs/blueprint/` wholesale. Never read or use old AIP code.
- The owner is cost-sensitive: read only what a task names, keep outputs short, run targeted tests
  while building and the full suite once before the PR.

## 2. Starter prompt (paste into a new conversation)

```text
You are ClaudeK. Read docs/handover/CLAUDEK-HANDOVER.md in ~/Project-AIP inside WSL
(wsl -d Ubuntu-24.04 --exec bash -lc 'cat ~/Project-AIP/docs/handover/CLAUDEK-HANDOVER.md')
and follow it. Check state (section 6), then start the next task from section 7.
Mark PRs ClaudeK, auto-fix CI, merge when all checks are green.
```

## 3. Environment (local, no cloud sessions)

The owner has no Claude cloud access on this account, so the repo's cloud `session-start.sh` hook never
runs (it exits unless `CLAUDE_CODE_REMOTE=true`). Everything runs in **WSL2, distro `Ubuntu-24.04`, user
`andrew`**, matching CI (Linux).

| What | Where / how |
|---|---|
| Working copy | **`~/Project-AIP` inside Ubuntu.** Do all git, build and test work here. |
| Windows copy | `C:\Users\Andrew\Project-AIP` is where the app session opens. Treat it as read-only; `git pull` it now and then so CLAUDE.md and this file stay current. Do not build or commit there (CRLF and speed problems). |
| Run a command | `wsl -d Ubuntu-24.04 --exec bash -lc '<command>'`. **Always use `--exec`**: without it, `wsl.exe` passes the line through an extra shell and `$variables` come out empty. Pipe output through `grep -v bogus` to drop a harmless terminal-size warning. |
| Write a file for WSL | Write it to the scratchpad on Windows, then copy it in with `tr -d "\r" < /mnt/c/... > ~/...` (strip CRLF). Heredocs inside `bash -lc` also work. |
| Tools in Ubuntu | Docker Engine (free, no Docker Desktop) + Compose, make, psql 16, uv (Python 3.12 and 3.13), Node 22, pnpm 10.28.0 (corepack), gh (signed in as `kingdonk-ops`), Playwright Chromium + WebKit. Git identity `kingdonk-ops <kingdonk@icloud.com>`. |
| Test Postgres | Testcontainers starts it per test session through Docker. Nothing to run. |
| Test Keycloak | A long-running compose Keycloak (project `aip-dev`, `localhost:8180`, restarts with Ubuntu). `~/aip-dev/keycloak.sh up\|down\|status\|logs\|reset`. `~/.profile` exports `AIP_TEST_KEYCLOAK_*` (CI's values), so the Keycloak flow tests use it automatically. Run `reset` after anything in `infra/keycloak/` changes. It holds ports 5432, 8180 and 8025. |
| Install deps | `make install` after a pull that changes `uv.lock` or `pnpm-lock.yaml`. |

**The PC is slow** (low-power i7-1065G7 laptop). A full `make check` takes about 30 minutes, and Keycloak
needs about 2 minutes to become healthy after Ubuntu starts. Timing-based tests that pass on CI can
fail here. Do not "fix" that by loosening product behaviour; widen only test waits, and say so in the PR.
Run long commands with a log file in the scratchpad and grep the result.

### Everything Claude Code (ECC)

The owner wants ECC used. **At handover time it is not installed on this PC** (only `github`,
`github-ops`, `github-contributor` and `auto-repo-setup` plugins are). The owner installs it, because
it adds third-party hooks that run on every session. Per its README, inside an interactive `claude`
session:

```text
/plugin marketplace add https://github.com/affaan-m/ECC
/plugin install ecc@ecc
```

Then check what it added (`/plugin`, the skills list) before relying on any of it. Notes:

- Rules are not part of the plugin; ECC's README describes copying them separately. Do not also run
  its full manual install on top of the plugin.
- `ECC_HOOK_PROFILE` (`minimal`, `standard`, `strict`) and `ECC_DISABLED_HOOKS` control its hooks. This
  repo's `.claude/settings.json` already sets `ECC_DISABLED_HOOKS=pre:config-protection`.
- Repo rule (CLAUDE-HANDOVER section 8): if any hook blocks you, stop and report it; never route around
  it, and never edit Claude settings or hooks unless the owner asks.
- Use ECC's planning, TDD, code-review and security-review agents or skills where they fit the loop
  in `AGENTS.md`. The loop and the hard rules still decide what "done" means.

## 4. PRs, CI and merging (owner instructions, 2026-10-12)

1. **Mark every PR:** title starts with `[ClaudeK] `, and add the `ClaudeK` label
   (`gh pr create ... --label ClaudeK`). The label already exists in the repo.
2. **Before merging, set the board row to `done` and add the PROGRESS line in the PR itself**, so
   the merge leaves the board true.
3. After `gh pr create`, check the PR with the app's PR tools (`get_status`, bind it if needed) and **turn
   on Auto-fix** for it. Do not poll CI yourself.
4. **If CI fails, fix it without asking:** read the job log, reproduce, fix the cause, push once. Never skip,
   disable or quarantine a test.
5. **When every check is green, squash-merge it yourself** (`gh pr merge <n> --squash`). Do not wait for
   the owner. GitHub auto-merge is not available: the repo has auto-merge off and `main` has no branch
   protection (that is an owner decision; do not change it).
6. Never rebase or force-push shared branches; merge `origin/main` into your branch. Commit with
   `git commit -m` (never `--no-verify`). End commit messages with the attribution trailer your session
   gives you.
7. **Coordinate with the other agent.** Before claiming a task: `git fetch`, `gh pr list --state open`,
   and check the board for `in-progress`/`review` rows. Claim early (board row `in-progress` with your
   branch in Notes, pushed). Two migration tasks must not run at the same time (one Alembic head). At most
   two build streams in total, ideally one API/database and one web UI.

## 5. Checks before opening a PR

```bash
python3 tools/next_task.py --check
make check            # ~30 min here; run it once, not per edit
uv run --python 3.13 pytest apps/api/tests/test_openapi_export.py -q   # when routes change
make generate-client  # when routes or schemas change; commit the result
uv run aip-db lint && uv run aip-db snapshot   # when a migration is added; commit the snapshot
```

## 6. State at handover (2026-10-12)

- `main` at `832c324` (PR #48 merged). **PR #49** (`[ClaudeK]` tracking sync) was open with Auto-fix on:
  it marks IDENTITY-02 (PR #37) and DESIGN-02 (PR #34) `done` and fills PR numbers in PROGRESS. If it is
  still open, finish it (green → squash-merge) before anything else.
- **IDENTITY-02 verified complete:** every spec step is implemented, every listed test exists, a
  security review ran (findings carried into IDENTITY-04), CI was green, and 213 identity + tenancy
  tests passed locally on 2026-10-12, including the real-Keycloak JIT test.
- **TESTING-10** (worker test waits for registration instead of a fixed sleep) is done (PR #48).
- Full local run before those fixes: 772 passed, 13 skipped; the only failures were the two timing
  issues now fixed.

Check current state with:

```bash
git fetch -q && git log --oneline -5 origin/main
gh pr list --state open
python3 tools/next_task.py --all
tail -n +18 tracking/PROGRESS.md | head -8
```

## 7. Next tasks (in this order)

1. **ACCESS-01**: permission catalogue from manifests, `PolicyService.can`, deny by default. It is on the
   M0 critical path (ACCESS-01 → PROJECTS-01 → PROJECTS-02 → TESTING-09) and unblocks over ten tasks.
   Its title says "Nest guard": translate it to a FastAPI dependency per ADR 0001. Security review
   required before merge (authorisation code).
2. In parallel, a **web stream: DESIGN-03** (register table standard). No migration, so it can run
   alongside ACCESS-01.
3. Then **PROJECTS-01** (needs ACCESS-01), **PROJECTS-02** (UI slice), and **IDENTITY-03** (server-side
   sessions; it adds a migration, so do not run it at the same time as another migration task). Pick up its
   "Carried forward from IDENTITY-02" notes.
4. **OPS-11** (Coolify demo) shows as ready, but it deploys with secrets. Ask the owner before starting
   it, and remind them that the Coolify API key must be rotated before any real data (it was pasted into
   an earlier chat).

Always re-check with `python3 tools/next_task.py --all`; the board decides.

## 8. Open items for the owner

- Rotate the Coolify API key before real data (see above).
- The repository is **public** and names the first customer. The owner should confirm that is intended.
- PR #47 (owner decisions of 2026-10-11) has no PROGRESS line or task ID; ask which ID to log it under.
- Branch protection / required checks on `main` (and the `boundaries` check) are still the owner's call.
- Other questions waiting on the owner: `tracking/OPEN-QUESTIONS.md`.

## 9. How to report

Plain and short: what merged, what is open, what is blocked and why, and any decision you need. If a
test failed or a step was skipped, say so. Never claim something is merged or green without checking.
