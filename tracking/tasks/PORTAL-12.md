# PORTAL-12 — Witness emails and pages in the recipient's own time zone

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`portal`](../../docs/blueprint/modules/portal/README.md) |
| Phase | R1 |
| Size | XS |
| Depends on | PORTAL-06, IDENTITY-11 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/portal/README.md`](../../docs/blueprint/modules/portal/README.md)
3. [`PORTAL-06.md`](PORTAL-06.md) (owner answer 5) and [`INSPECTIONS-12.md`](INSPECTIONS-12.md) (D9)
4. ADRs: 0025

## Spec

Owner 2026-11-03: site time is fine for R1, but later the witness email must show the time in the recipient's own
time zone (tag: extend).

- **files**:
  - apps/api/aip/modules/portal/witness_email.py
  - apps/portal/src/witness/format.ts
  - apps/api/aip/modules/portal/tests/test_witness_email.py
  - apps/portal/src/witness/__tests__/format.test.ts
- **steps**:
  - 1. The email shows the booked time first in the recipient's preferred zone (IDENTITY-11) with its abbreviation,
    then the site's time and zone when they differ, then UTC. With no preference set, it keeps the PORTAL-06 format.
  - 2. The portal pages use the same order: the viewer's preferred zone, else the browser's zone, then site time.
  - 3. Reminder emails (PORTAL-11) use the same formatter.
- **acceptance**:
  - A Sydney recipient of a Perth booking at 9:00 am AWST reads 12:00 pm AEDT first, then 9:00 am AWST, then UTC.
- **tests**:
  - **unit**:
    - email: recipient `Australia/Sydney`, site `Australia/Perth` → AEDT first, AWST second, UTC third; recipient in
      Perth → AWST and UTC only; no preference → PORTAL-06 format
    - format.ts: preferred zone wins over the browser zone
