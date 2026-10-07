# ADR 0007: Walking skeleton first, trimmed P0, Release 1 "Kaefer live"; AIP keeps running

- **Status:** proposed: **owner to confirm the cut and a target date**
- **Date:** 2026-10-07
- **Affects:** build order, the board, every phase

## Context

The blueprint has 64 modules, and P0 alone has 15 modules before Kaefer sees anything new. The
SaaS, enterprise and development-lead reviewers all judged this the biggest delivery risk.
Several P0 tasks also assume AIP code or data that isn't in this repo (docs/reviews/07-delivery.md).

## Decision

1. **AIP (FastAPI) stays in production for Kaefer**, with fixes only, until R1 cutover and a reconciled data
   migration. Its database must be backed up now.
2. **M0 walking skeleton first:** two tenants, Keycloak sign-in, Next.js shell, a Projects register with RLS
   isolation proven in CI, deployed to AWS staging. See the M0 section of the board.
3. **P0 is split** into P0-core (what P1 consumes) and P0-hardening, which runs alongside P1.
   Tasks that need P1/P2 modules move out: DATABASE-03 → P1 data_io (AIP migration), TENANCY-04 → P2,
   TESTING-06 → split into P1/P2, TESTING-07 → P2, TERMS-04 → P4, TERMS-06 → P1.
   SECURITY-03/04/05 become hardening; buy Vanta/Drata for the control catalogue and evidence.
4. **R1 "Kaefer live"** = P0-core + assets, item types, forms (operator-authored JSON templates),
   inspections/ITPs/hold points, certificate hard-block, RSW completion gate, NCR basics, Gotenberg PDF
   reports (pulled forward from P2) and AIP data migration. Designers, offline PWA, portal, P3 and P4 come later.
5. **Scope governance:** scout suggestions marked "accepted" go to a backlog. A module enters a phase only
   with a paying customer or a need demonstrable in the pilot.

## Consequences

P1+ tasks are generated just in time by the `PLAN-*` tasks on the board (process in docs/reviews/07-delivery.md).
