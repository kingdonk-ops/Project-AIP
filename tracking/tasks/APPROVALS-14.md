# APPROVALS-14 — Approval route completion enforces the target transition's comment rule

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`approvals`](../../docs/blueprint/modules/approvals/README.md) |
| Phase | R1 |
| Size | XS |
| Depends on | APPROVALS-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/approvals/README.md`](../../docs/blueprint/modules/approvals/README.md)
3. [`docs/reviews/13-merged-pr-review-2026-11-03.md`](../../docs/reviews/13-merged-pr-review-2026-11-03.md) (M2, L9, L10)
4. ADRs: 0035, 0040

## Spec

Make a finished route run every check a direct transition runs (ADR 0040 point 1) (tag: harden).

- **files**:
  - apps/api/aip/modules/approvals/transition.py (`complete_route`)
  - apps/api/aip/modules/approvals/routes_engine/service.py
  - config/terms/en-AU/approvals.json
  - apps/api/aip/modules/approvals/tests/test_routes_db.py
- **steps**:
  - 1. `complete_route` applies the target transition's `requires_comment`: the finishing decision's comment is the
    transition comment, and a blank one is 422 `COMMENT_REQUIRED` (`approvals.comment.required`). Move the check out of
    the direct path (`transition.py:443`) into one helper both paths call.
  - 2. Run the transition checks (guard, comment, step-up) before `decide_step` / `skip_steps` write, so a refusal
    never relies on rollback.
  - 3. Add the en-AU term for `approvals.route.pending`.
- **acceptance**:
  - A route whose `on_approved_action` requires a comment cannot complete on a decision without one, and nothing is
    written.
  - Every message key the approvals module raises has an en-AU term.
- **tests**:
  - **unit**:
    - every `messageKey` raised in approvals resolves in en-AU
  - **integration**:
    - route ending in `retire`: last approval without a comment → 422 `COMMENT_REQUIRED`, step and instance
      unchanged; with a comment → completes and the transition record carries it
