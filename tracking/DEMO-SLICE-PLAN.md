<!-- hand-edited: owner-requested demo-slice sequencing (2026-10-24); regeneration must keep this file -->
# Demo slice plan — fastest path to a usable operational demo

Board: [BOARD.md](BOARD.md) · Scope ADR: [0007](../docs/adr/0007-mvp-scope-and-strangler.md) · R1 decisions: [ADR 0036](../docs/adr/0036-r1-module-decisions.md)

This is a **build-order view**, not a new scope. Every task below already lives on the board in its
module/wave section; status is tracked there. This file (and the "Demo slice" section on the board)
only reorders the R1 critical path into the shortest sequence that reaches a demoable operational
loop, so the two build streams (ADR 0007: at most two at once) can pick straight from it.

## What "usable operational demo" means

One vertical slice a Kaefer user can actually drive end to end:

> Sign in → build an asset tree → publish a form template → run an inspection against an asset
> (validated answers, ITP hold/witness points) → approve → generate the PDF report.

M0 (login, projects register, RLS isolation, Coolify deploy) is already merged, so the demo gap is
this R1 slice on top of it.

- **Scope A (on-screen core):** asset → form → inspection → approval, no PDF. Drops the whole
  uploads→reports branch (OPS-17 feeder aside, which is still worth doing for import/jobs).
- **Scope B (recommended):** Scope A **+ the Gotenberg PDF report**. This is the "full operational
  loop" the sequencing below targets.
- **Portal sign-off add-on:** client is invited, signs in to the portal, reviews/releases a hold
  point and signs off, views the client report. Separate stream in its own section — pull it in if
  there is time; it does not block Scope B.

## Critical path (the floor)

Six serial "M" tasks on the backend; nothing can beat this depth:

```
ASSETS-01 → FORMS-01 → FORMS-02 → INSPECTIONS-01 → INSPECTIONS-02 → REPORTS-03
```

Feeder branches that must land before their consumer but do not lengthen the path:

- **Forms enablers:** ITEMTYPES-01 + APPROVALS-08 → FORMS-01
- **Inspection lifecycle:** APPROVALS-05 → INSPECTIONS-01
- **Report render:** OPS-17 → UPLOADS-02 → UPLOADS-08 → REPORTS-02 (+ REPORTS-01, IDENTITY-09) → REPORTS-03

**Watch item — OPS-17** is `todo`, ready now, and a hidden chokepoint: it blocks UPLOADS-02,
REPORTS-02 and all import/reminder jobs. Start it in round 1 whatever the scope.

**Watch item — usable means screens.** The only specced inspection UI (INSPECTIONS-04) is gated on
INSPECTIONS-03 (ITP/hold points, also the R1 midpoint that gates PLAN-P2), so a usable inspection
page pulls INSPECTIONS-03 in. Kept deliberately — it is the most demo-worthy Kaefer feature.

## Core demo slice — build order (Scope B)

Two streams: **[api]** = API/DB/worker, **[web]** = web UI. A round is a readiness gate, not a
sprint; within a round, order by the critical path (ASSETS-01 and OPS-17 first).

### Round 1 — ready to start today (all deps already `done`)

| Order | Task | Stream | Why it is here |
|---|---|---|---|
| 1 | ASSETS-01 | api | Critical path; unblocks every R1 module |
| 2 | OPS-17 | api | Chokepoint: unblocks uploads, reports and import/reminder jobs |
| 3 | ITEMTYPES-01 | api | Feeds FORMS-01 field types and asset attributes |
| 4 | APPROVALS-08 | api | Precondition of FORMS-01 (guard evaluator + preset installer) |
| 5 | APPROVALS-05 | api | Inspection lifecycle preset for INSPECTIONS-01 |
| 6 | REPORTS-01 | api | Report template + HTML render contract |
| 7 | IDENTITY-09 | api | Display-name lookup for REPORTS-03 |
| 8 | ACCESS-07 | api | `move` verb; precondition of ASSETS-03 |
| — | TESTING-12 | web | Harden the *current* demo: live-Keycloak journeys |
| — | TESTING-13 | web | Seed a demo workflow + approvals journeys into `e2e-skeleton` |
| — | PROJECTS-07 | web | Project detail page — presentable current demo |

### Round 2 — forms + uploads land

| Order | Task | Stream | Deps cleared by |
|---|---|---|---|
| 1 | FORMS-01 | api | ITEMTYPES-01, APPROVALS-08 |
| 2 | FORMS-02 | api | FORMS-01 (shared JSONLogic evaluator) |
| 3 | ITEMTYPES-02 | api | ITEMTYPES-01 (schema versions) |
| 4 | UPLOADS-02 | api | OPS-17 (scan worker) |
| 5 | UPLOADS-08 | api | UPLOADS-02 (server-side file access) |
| 6 | ASSETS-02 | api | ASSETS-01, ITEMTYPES-02 |
| 7 | FORMS-03 | web | FORMS-02 (form renderer package) |
| 8 | FORMS-04 | web | FORMS-01 (template register/detail) |
| 9 | ITEMTYPES-03 | web | ITEMTYPES-02 (admin pages) |

### Round 3 — inspections + report render

| Order | Task | Stream | Deps cleared by |
|---|---|---|---|
| 1 | INSPECTIONS-01 | api | APPROVALS-05, ASSETS-01, FORMS-01 |
| 2 | INSPECTIONS-02 | api | FORMS-02, INSPECTIONS-01 |
| 3 | INSPECTIONS-03 | api | INSPECTIONS-02 (ITP/hold points; R1 midpoint) |
| 4 | REPORTS-02 | api | OPS-17, REPORTS-01, UPLOADS-08 (Gotenberg render job) |
| 5 | ASSETS-03 | web | ACCESS-07, ASSETS-02, ITEMTYPES-03 (asset tree + register) |

### Round 4 — close the loop

| Order | Task | Stream | Deps cleared by |
|---|---|---|---|
| 1 | REPORTS-03 | api | IDENTITY-09, INSPECTIONS-02, REPORTS-02 (PDF on approval) |
| 2 | INSPECTIONS-04 | web | FORMS-03, INSPECTIONS-03, UPLOADS-08 (register/detail + renderer) |
| 3 | REPORTS-04 | web | REPORTS-02 (report register + authorised download) |

**Core slice total: ~21 tasks** (vs. ~90 for full R1). Scope A drops OPS-17's uploads/reports
consumers, UPLOADS-02, UPLOADS-08, REPORTS-01/02/03/04 and IDENTITY-09 — about 7 fewer tasks and one
whole chain branch.

## Portal sign-off add-on — build order

Independent stream. Start the two ready-now leaves early so it overlaps the core slice; the rest
join once ASSETS-01 / INSPECTIONS-03 / REPORTS-04 from the core slice have merged.

| Round | Task | Stream | Deps cleared by |
|---|---|---|---|
| P1 | IDENTITY-10 | api | ready now (PLAN-R1) — portal audience sign-in/cookies/invites |
| P1 | ACCESS-04 | api | ready now (ACCESS-02, ARCH-07) — teams for approver routing |
| P2 | PORTAL-01 | api | ASSETS-01 — external users + grants |
| P2 | APPROVALS-04 | api | ACCESS-04, APPROVALS-02 — sequential/parallel approver steps |
| P3 | PORTAL-02 | api | IDENTITY-10, PORTAL-01 — portal sign-in/session on own host |
| P3 | INSPECTIONS-05 | api/web | APPROVALS-04, INSPECTIONS-03, PORTAL-01 — client review step + sign-off chips |
| P4 | PORTAL-03 | web | INSPECTIONS-05, PORTAL-02 — portal app, sign-in, needs-my-action inbox |
| P5 | PORTAL-04 | web | INSPECTIONS-05, PORTAL-03 — client review + hold-point release with sign-off assurance |
| P5 | PORTAL-05 | web | PORTAL-03, REPORTS-04 — client reports in the portal |

Optional portal polish for the demo (not required for the sign-off loop): PORTAL-07 (external-users
admin), PORTAL-08 (access-expiry reminders), PORTAL-06 (witness attendance, needs PROJECTS-04).

## Notes

- Dependencies are taken from BOARD.md, which overrides the ones inside task files (AGENTS.md).
- `done` deps as of 2026-10-24: PLAN-R1, APPROVALS-02, ACCESS-02, ACCESS-03, ARCH-07, TERMS-01,
  DESIGN-01/03/04, UPLOADS-01, OPS-02, ARCH-05, IDENTITY-04.
- Several R1 rows still carry "convert to Python backend per ADR 0001 before starting" — honour that
  on each before building.
