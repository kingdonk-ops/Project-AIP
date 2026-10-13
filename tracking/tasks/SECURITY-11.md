# SECURITY-11 — Stop gitleaks false positives at the source

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`security`](../../docs/blueprint/modules/security/README.md) |
| Phase | P0 |
| Size | XS |
| Depends on | SECURITY-08 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. `.gitleaksignore`

## Spec

Owner request (2026-10-13). A gitleaks fingerprint names one commit, and squash merges create new
commits, so each reviewed false positive had to be listed twice (PRs #56 and #58). Reshape the lines
that only look like secrets so gitleaks no longer flags them, and record the rule.

- **files**:
  - apps/api/aip/modules/projects/settings.py
  - .gitleaksignore
- **steps**:
  - 1. `gitleaks dir` over the working tree: the only finding is the projects cursor-key `Field(...)`, where the env var name and `min_length=16` on one line read as a key and a value. Put one argument per line.
  - 2. Add guidance at the top of `.gitleaksignore`: fix the line rather than add an entry; existing entries stay for the history.
- **acceptance**:
  - `gitleaks dir` on the working tree and `gitleaks git` on the full history both report no leaks.
- **tests**:
  - **unit**:
    - the projects settings tests still pass.
  - **integration**:
    - none
  - **e2e**:
    - none
