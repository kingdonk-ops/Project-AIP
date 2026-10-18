# ADR 0035: Transition service: how the APPROVALS-02 spec meets the Python code

- **Status:** accepted
- **Date:** 2026-10-18
- **Affects:** approvals, identity, access; APPROVALS-02 (with APPROVALS-03 merged), APPROVALS-04, APPROVALS-05, APPROVALS-07

## Context

APPROVALS-02 was written for the old NestJS stack (`transition.service.ts`, nestjs-zod,
`json-logic-js`) and before IDENTITY-04 shipped `check_signoff_assurance` (ADR 0034). Converting it
to the Python backend (ADR 0001) left several gaps the spec does not settle.

## Decision

1. **Guards use an in-house evaluator.** Python has no maintained port of `json-logic-js`.
   `guards/jsonlogic.py` implements only the 17 allow-listed operators
   (`== != === !== < <= > >= ! !! and or if var missing missing_some in`) with jsonlogic.com
   semantics, refuses everything else, caps a guard at depth 20, 200 nodes and 8 KB, and evaluates
   over deep-frozen facts. A small, closed evaluator is easier to audit than a dependency.
2. **The guard runs before the sign-off check.** The spec lists the sign-off check (e) before the
   guard (f). Both happen before any write, so the order changes no evidence, but a guard that will
   refuse must not first ask the person to step up.
3. **`STEP_UP_REQUIRED` is 401** with the ADR 0015 body, as ADR 0034 decided for every critical
   action (the spec said 403). The countersign flow:
   - `countersign_required` appends the decision with `status = 'pending_countersign'`, bumps
     `sync_version` and leaves `current_state` alone; the response is 202 and no
     `workflow.transitioned` event is emitted.
   - While it waits, only the same action may be taken (409 `COUNTERSIGN_PENDING`), never by its
     signer (409 `SELF_COUNTERSIGN`). The countersigner needs the transition's permission, a passing
     guard and an `allow` (otherwise 401 step-up or 403 `COUNTERSIGN_ASSURANCE_REQUIRED`).
   - Their decision is an `applied` row whose `countersigns_id` names the pending one. Rows are
     never updated.
4. **Assurance is stored on every decision**, not only critical ones: `assurance_level`,
   `assurance_method`, `authenticated_at`, `device_id`, and `auth_strength` mapped from the method
   (`password`, `pin`, or `mfa`). `aal2_available` is true when the session is aal 2 or the user's
   `mfa_enrolled_at` is set (identity stamps it on the first aal 2 session, brokered or local). A
   critical transition is checked against its `signoffAction` (a new optional spec field), else
   `workflow.<action>`.
5. **The hash covers more than the spec's list.** `entry_hash` also covers the row's `id`,
   `supersedes_id`, `status`, `countersigns_id` and the four assurance columns, so no stored field
   can change unnoticed. The canonical form is RFC 8785 via the `rfc8785` library AUDIT-01 already uses
   (`audit/api.py` exports no helper). `workflow_decision_history` is not range-partitioned, for
   the same reason as `audit_log` (ADR 0031): `unique (instance_id, seq)` needs no partition key.
6. **Every route is `authenticated()` and the service checks each permission** against the
   instance's project: `approvals.view` to see or act on an instance, `approvals.start` to start
   one (new in the catalogue), and the transition's `requiredPermission`. The project is known only
   once the instance is loaded, and route-level `requires()` would ignore project-scoped grants.
   Another tenant's instance is 404 before any permission check.
   **A client never chooses a record's project.** Instances are unique per record, so a caller
   who could name the project could bind someone else's record to a weaker workflow. A host module
   registers a `RecordResolver` for its record type with `register_record_resolver`.
   `POST /instances` then behaves like this:
   - with no resolver for the record type it refuses (422 `UNKNOWN_RECORD_TYPE`);
   - when the resolver cannot see the record it returns 404;
   - otherwise it checks `approvals.start` on the resolved project;
   - a `projectId` in the body that disagrees with the resolved one is 422 `PROJECT_MISMATCH`.

   `ApprovalsApi.start_instance` trusts its caller's project, because the host module calling it
   already knows its own record.
7. **Validation errors are 422**, as everywhere else in this API (FastAPI's
   `RequestValidationError`). The spec's "unknown key → 400" came from nestjs-zod. Request bodies
   forbid unknown keys, so a client still cannot send a guard outcome. JSON is camelCase
   (`currentState`, `entryHash`) as in every other module. The history response never includes
   the stored client IP.
8. **Small cross-module exports:**
   - identity's `api.py` now exports `StepUpRequiredError` and `mfa_enrolled_at`;
   - access's `api.py` exports `role_codes(conn, user_id, project_id)`, which gives a guard its
     `actor.roles`.

   The guard facts provider takes `(conn, record_id)`: the transition's tenant connection, not a
   request context. It runs inside a savepoint, so its SQL error cannot abort the transition. Its
   facts must be JSON: `Decimal` becomes a number, dates become ISO strings, and anything else
   fails closed (422 `GUARD_ERROR`), so numbers are never compared as text.
9. **The Playwright API journeys are carried forward** to APPROVALS-07. No record type exists
   whose definition, permissions and fixture users a deployed stack could seed, and the
   `approvals.demo.*` codes are test-only (added to the catalogue in the tests, never to the
   manifest). The integration tests run the same HTTP journeys in-process.

## Consequences

- APPROVALS-04 adds steps and delegation (`step_id`, `on_behalf_of`) to the existing columns.
- APPROVALS-05 gives its inspection lifecycle real permission codes and a guard facts provider.
- APPROVALS-07 seeds a demo workflow on the compose stack and runs the API journeys there.
- A deployed definition whose `requiredPermission` is not in the catalogue denies every caller
  (`unknown_permission`). A publish-time check is left to the definition editor.
