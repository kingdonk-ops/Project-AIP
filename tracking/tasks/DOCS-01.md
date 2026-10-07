# DOCS-01 — Board, ADRs, agent workflow, conventions fixes

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`arch`](../../docs/blueprint/modules/arch/README.md) |
| Phase | P0 (setup) |
| Size | S |
| Depends on | — |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Spec

Make the repo usable by agents before any code is written. **Done in the setup PR.**

- **files**:
  - `AGENTS.md`, `CLAUDE.md`, `README.md`
  - `tracking/BOARD.md`, `tracking/PROGRESS.md`, `tracking/OPEN-QUESTIONS.md`, `tracking/tasks/_TEMPLATE.md`
  - `docs/adr/0000`–`0008`, `docs/reviews/01`–`07`, `docs/blueprint/**`
  - `tools/split_blueprint.py`, `tools/next_task.py`, `.github/workflows/tracking.yml`, `.github/pull_request_template.md`
- **acceptance**:
  - `python3 tools/next_task.py --check` reports 0 errors.
  - `python3 tools/next_task.py` names a wave-0 task and the exact files to read.
  - Every contradiction raised in the reviews is either resolved by an ADR or listed in OPEN-QUESTIONS.md.
