# SECURITY-05 — Quarterly access review generator

| Field | Value |
|---|---|
| Module | [`security`](../../docs/blueprint/modules/security/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | SECURITY-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/security/README.md`](../../docs/blueprint/modules/security/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Generate review rows from users, roles and teams with keep/revoke and sign-off.

- **depends on**:
  - SECURITY-02
- **files**:
  - backend/app/modules/security/access_review.py
  - backend/tests/security/test_access_review.py
- **steps**:
  - 1. Generate one row per active user-role-scope assignment with last login.
  - 2. Allow decisions keep or revoke per row.
  - 3. Executing a revoke calls the existing role-assignment removal.
  - 4. Sign-off requires all rows decided and the signer is not the reviewee.
  - 5. Freeze the review after sign-off, store an export hash as evidence_items, and block edits.
  - 6. Provide a review-due notification based on cadence.
- **acceptance**:
  - Sign-off is blocked while any row is undecided.
  - A revoke removes the access.
  - A signed review is immutable.
- **tests**:
  - **e2e**:
    - Reviewer opens /security/access-reviews, decides all rows, signs off, and downloads the export.
  - **integration**:
    - Generate for 3 users x 2 roles gives 6 rows.
    - Revoke a row: the user's permission check then denies.
    - Sign off with 1 undecided row returns 409.
    - Edit after sign-off returns 409.
  - **unit**:
    - The self-review check rejects reviewer==user.
