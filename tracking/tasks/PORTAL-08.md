# PORTAL-08 — Access expiry reminders to the project admin (30, 20, 10 and 1 days before), renew or ignore, expiry notices to admin and client

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

Remind the project admins (holders of `portal.grant.manage` on the grant's project, else the tenant admins) by email (STACK-06 mailer) 30, 20, 10 and 1 days before a client's access to their project expires, from a daily job (OPS-13 scheduler, OPS-17 tenant fan-out) with a reminder log so each reminder is sent once per grant period. Each email links to renew the access for another project access period (`portal_access_days`, 180 by default, up to 400) or to ignore the reminders. Renewing stops further reminders. Ignoring stops the remaining reminders for that period only; a later renewal starts a new period with reminders again. If the access is not renewed, the admins always get a notice on the day it expires, saying it has expired and how to renew it, whether or not they ignored the reminders (owner, 2026-10-18). The same day the client gets an email saying their access to that project has expired, that the project admin renews it if it is still needed, that the project admin has been told, and that the client needs to do nothing (owner, 2026-10-18). The client gets no reminders before expiry. Calendar days are counted in UTC (ADR 0025) (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).
