# PORTAL-08 — Access expiry reminders to the project admin (30, 20, 10 and 1 days before), renew or ignore, expiry notice

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`portal`](../../docs/blueprint/modules/portal/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | OPS-17, PORTAL-07 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/portal/README.md`](../../docs/blueprint/modules/portal/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)

## Spec

Remind the project admins (holders of `portal.grant.manage` on the grant's project, else the tenant admins) by email (STACK-06 mailer) 30, 20, 10 and 1 days before a client's access to their project expires, from a daily job (OPS-13 scheduler, OPS-17 tenant fan-out) with a reminder log so each reminder is sent once per grant period. Each email links to renew the access for another project access period (`portal_access_days`, 180 by default, up to 400) or to ignore the reminders. Renewing stops further reminders. Ignoring stops the remaining reminders and the expiry notice for that period, and a later renewal starts a new period with reminders again. If the access is neither renewed nor ignored, the admins get a notice on the day it expires saying it has expired and how to renew it. Calendar days are counted in UTC (ADR 0025) (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).
