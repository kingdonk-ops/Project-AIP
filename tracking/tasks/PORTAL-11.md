# PORTAL-11 — Witness booking reminders before the booked time and notice-period-ending alerts

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`portal`](../../docs/blueprint/modules/portal/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | PORTAL-06 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/portal/README.md`](../../docs/blueprint/modules/portal/README.md)
3. [`PORTAL-06.md`](PORTAL-06.md) (owner answer 6) and [`PORTAL-08.md`](PORTAL-08.md) (the reminder job pattern)
4. ADRs: 0025, 0030, 0032

## Spec

Owner 2026-11-03: send reminders before a booked witness or hold point and alert when its notice period is ending
(tag: extend).

- **files**:
  - apps/api/aip/modules/portal/witness_reminders.py (new), jobs.py, manifest.toml
  - apps/api/aip/modules/portal/witness_email.py (reminder and alert kinds)
  - config/terms/en-AU/portal.json
  - apps/api/aip/modules/portal/tests/test_witness_reminders_db.py
- **steps**:
  - 1. An hourly per-tenant job (OPS-13 trigger, ADR 0032 fan-out) finds open bookings and sends:
    - to each current recipient (PORTAL-06 D5): a reminder 24 h before `scheduled_start_utc` if the booking is not
      rejected, and a second one 2 h before if it is accepted;
    - to the requester: an alert when a proposed booking still has no client response and less than 25 % of its
      notice period remains, and when the booked time passes with no response.
  - 2. Each send has an idempotency key `witness:{bookingId}:r{revision}:{kind}:{userId}`, so a rerun, overlap or
    reschedule never sends twice for one revision; a reschedule starts a new set.
  - 3. Each send is recorded on the booking (a `reminded` event: kind, recipient count), so the history shows it.
- **acceptance**:
  - A client gets exactly one 24 h reminder per booking revision; the requester gets one "no response" alert.
  - Cancelled, done and rejected bookings get no client reminders.
- **tests**:
  - **unit**:
    - schedule table: start in 30 h → none; 23 h → 24 h reminder; accepted at 1 h 50 m → 2 h reminder; rejected →
      none
  - **integration**:
    - run the job twice at the same fixture time → one email per recipient; reschedule → a new reminder; tenant B's
      bookings are never read in tenant A's run
