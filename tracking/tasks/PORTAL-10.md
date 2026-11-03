# PORTAL-10 — Client waives a booked witness or hold point in the portal ("proceed without me")

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`portal`](../../docs/blueprint/modules/portal/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | PORTAL-06, INSPECTIONS-12 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/portal/README.md`](../../docs/blueprint/modules/portal/README.md)
3. [`PORTAL-06.md`](PORTAL-06.md) (owner answer 2) and [`INSPECTIONS-12.md`](INSPECTIONS-12.md) (D4, D11)
4. ADRs: 0010, 0036, 0039

## Spec

Owner 2026-11-03: the client may waive a booked witness or hold point ("proceed without me"). It is a client
sign-off on the point, so it is an ADR 0010 critical action (tag: extend).

- **files**:
  - apps/api/aip/modules/portal/witness.py, routes.py, schemas.py
  - apps/portal/src/witness/{WitnessDetail.tsx,WaiveDialog.tsx}
  - apps/portal/src/witness/__tests__/witness-detail.test.tsx
  - config/terms/en-AU/portal.json
  - apps/api/aip/modules/portal/tests/test_witness_routes_db.py
  - e2e/portal/witness.spec.ts
- **steps**:
  - 1. `POST /api/v1/portal/witness/{bookingId}/waive` `{reason, expectedRevision, clientRequestId}`: needs the
    grant's `witness` action on the booking's scope (404 otherwise) and calls `InspectionsApi.waive_by_client`. Missing
    assurance → 401 `STEP_UP_REQUIRED`; the page runs the portal step-up and retries. Replays return 200.
  - 2. The detail page shows "Proceed without me" while the booking is open. The dialog explains that the work will
    go ahead without the client and that this is recorded as their sign-off; a reason is required.
  - 3. The requester gets the `responded` email with "waived" and the reason (PORTAL-06 step 2 composition).
- **acceptance**:
  - A client with `witness` on the asset waives an open booking after step-up; the step is `waived`, the sign-off
    row has `signatory_role: client` and the requester is emailed.
  - A client without step-up cannot waive; a client outside the grant gets 404; a closed booking offers no waive.
- **tests**:
  - **unit**:
    - WaiveDialog: no reason blocks submit; 401 starts step-up then retries; axe has no serious or critical violation
  - **integration**:
    - waive with aal2 → 201, step waived, client sign-off chained, `portal.witness_responded` security event; aal1 →
      401; other grant → 404; replay → 200 with one sign-off
  - **e2e**:
    - client waives after step-up → status waived and the supervisor gets one email; cross-tenant 404; axe; mobile
