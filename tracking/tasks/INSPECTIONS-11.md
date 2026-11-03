# INSPECTIONS-11 — ITP sign-off hardening: supervisor-only countersign, server-set signatory role, client refusal code, responses FK, supervisor edit

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`inspections`](../../docs/blueprint/modules/inspections/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | INSPECTIONS-03 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/inspections/README.md`](../../docs/blueprint/modules/inspections/README.md)
3. [`docs/reviews/13-merged-pr-review-2026-11-03.md`](../../docs/reviews/13-merged-pr-review-2026-11-03.md) (M6, L6 to L8)
4. ADRs: 0010, 0035, 0041

## Spec

Bring INSPECTIONS-02 and -03 in line with ADR 0010 and ADR 0041 §6 (tag: harden).

- **files**:
  - apps/api/aip/modules/inspections/itp.py, itp_rules.py, schemas.py, policies.py
  - apps/api/migrations/versions/202611100900_inspections_responses_fk.py (new forward-only revision; take the real timestamp when building)
  - config/terms/en-AU/inspections.json
  - apps/api/aip/modules/inspections/tests/
- **steps**:
  - 1. **Countersign by a supervisor (ADR 0010).** A pending sign-off is countersigned only by a user holding the
    supervisor permission on the project (`approvals.inspection.review`) with the required assurance. Any other
    `itp.sign` holder gets 403 `COUNTERSIGN_SUPERVISOR_REQUIRED`.
  - 2. **Signatory role from the server.** `signatory_role` is derived from the signer's grants (inspector or
    supervisor); a request may only narrow it (a supervisor signing as inspector). Claiming `supervisor` or
    `third_party` without the matching grant is 403.
  - 3. **Client sign-off refusal.** `signatoryRole: "client"` answers 422 `CLIENT_SIGNOFF_NOT_AVAILABLE` with an en-AU
    term, until the portal builds client sign-off.
  - 4. **Responses FK (L7).** A forward-only migration adds the composite FK `inspection_responses (inspection_id,
    tenant_id) → inspections (id, tenant_id)`; DATABASE-09 made this work on partitioned append-only tables.
  - 5. **Supervisor edit (L8).** In `supervisor_review`, a user with `approvals.inspection.review` may save answers
    without `inspection.respond` (ADR 0041 §6).
- **acceptance**:
  - An inspector cannot countersign another inspector's pending sign-off; a supervisor can.
  - A caller cannot record a signatory role their grants do not give them.
  - A response row cannot reference a missing inspection.
- **tests**:
  - **integration**:
    - inspector countersign → 403; supervisor countersign → applied, and the chain verifies
    - inspector claiming `supervisor` → 403; supervisor signing as inspector → recorded as inspector
    - `signatoryRole: "client"` → 422 `CLIENT_SIGNOFF_NOT_AVAILABLE`
    - insert a response for an unknown inspection id → FK violation; the FK is present on every partition
    - supervisor with review but without respond saves an answer in `supervisor_review` → 200
