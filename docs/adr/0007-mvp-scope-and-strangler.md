# ADR 0007: Walking skeleton first, trimmed P0, Release 1 "Kaefer live"

- **Status:** proposed: **owner to confirm the cut and a target date**
- **Date:** 2026-10-07
- **Affects:** build order, the board, every phase

## Context

The blueprint has 64 modules, and P0 alone has 15 modules before Kaefer sees anything new. The
SaaS, enterprise and development-lead reviewers all judged this the biggest delivery risk.
Several P0 tasks also assume AIP code or data that isn't in this repo (docs/reviews/07-delivery.md).

## Decision

1. **Whatever Kaefer uses today keeps running** until R1 cutover. AIP code is not used (ADR 0001).
   Kaefer's existing records arrive as an owner-provided export and are imported and reconciled in R1.
2. **M0 walking skeleton first:** two tenants, Keycloak sign-in, web app shell, a Projects register with RLS
   isolation proven in CI, deployed to **Coolify** (owner, 2026-10-07) with synthetic data only. The AWS staging
   pipeline (OPS-07, OPS-09, OPS-10) is built later in P0-core, before any real customer data is loaded.
3. **P0 is split** into P0-core (what P1 consumes) and P0-hardening, which runs alongside P1.
   Tasks that need P1/P2 modules move out: DATABASE-03 → P1 data_io (import of Kaefer records from an export), TENANCY-04 → P2,
   TESTING-06 → split into P1/P2, TESTING-07 → P2, TERMS-04 → P4, TERMS-06 → P1.
   SECURITY-03/04/05 become hardening; buy Vanta/Drata for the control catalogue and evidence.
4. **R1 "Kaefer live"** = P0-core + assets, item types, forms (operator-authored JSON templates),
   inspections/ITPs/hold points, certificate hard-block, RSW completion gate, NCR basics, Gotenberg PDF
   reports (pulled forward from P2) and import of Kaefer's existing records from an export. Designers, offline PWA, portal, P3 and P4 come later.
5. **Scope governance:** scout suggestions marked "accepted" go to a backlog. A module enters a phase only
   with a paying customer or a need demonstrable in the pilot.

## Consequences

P1+ tasks are generated just in time by the `PLAN-*` tasks on the board (process in docs/reviews/07-delivery.md).
