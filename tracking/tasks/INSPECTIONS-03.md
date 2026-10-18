# INSPECTIONS-03 — ITP steps with hold and witness points, release-to-proceed and sign-off assurance

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`inspections`](../../docs/blueprint/modules/inspections/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | INSPECTIONS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/inspections/README.md`](../../docs/blueprint/modules/inspections/README.md) ("What it does", "Features" ITP bullets) and [`data-model.md`](../../docs/blueprint/modules/inspections/data-model.md) (`itp_steps`, `inspection_signoffs` only)
3. [INSPECTIONS-01](INSPECTIONS-01.md) and [INSPECTIONS-02](INSPECTIONS-02.md) (the module, the guard facts provider, `get_current_responses`)
4. ADRs: [0010](../../docs/adr/0010-signoff-assurance.md) (sign-off assurance, countersign fallback; the owner answers on client sign-off are **not** built here), [0035](../../docs/adr/0035-transition-service-implementation.md) §3–5 (how approvals applies the same check: 401 `STEP_UP_REQUIRED`, `pending_countersign`, `SELF_COUNTERSIGN`, assurance on every decision, RFC 8785 hash chain), [0031](../../docs/adr/0031-audit-log-not-partitioned.md) (a chain with a table-wide unique key is not partitioned), [0021](../../docs/adr/0021-retention-schedule.md) (hold-point sign-offs kept 7 years), [0025](../../docs/adr/0025-time-and-timezones.md), [0036](../../docs/adr/0036-r1-module-decisions.md) (choices 7 and 8)
5. Code to build on: `apps/api/aip/modules/identity/api.py` (`check_signoff_assurance`, `SignoffContext`, `SessionFacts`, `derive_assurance`, `mfa_enrolled_at`, `StepUpRequiredError`), `apps/api/aip/modules/identity/assurance.py` (only to read the action codes `hold_point.release`, `witness.countersign`, `itp.signoff`), `apps/api/aip/modules/approvals/transition.py` and `decision_chain.py` (the pattern to mirror, not to import), `apps/api/migrations/versions/202610181200_approvals_decision_history.py`

## Spec

Give ITP-kind inspections ordered steps with hold, witness, review and surveillance points, where a hold blocks later steps until it is released, every release or witness is a signed, hash-chained `inspection_signoffs` record that passes identity's sign-off assurance check (ADR 0010) or waits for a countersign, and other modules can ask whether a step is released or put an NCR hold on it (tag: extend).

- **files**:
  - apps/api/migrations/versions/<timestamp>_inspections_itp_signoffs.py
  - apps/api/aip/modules/inspections/tables.py
  - apps/api/aip/modules/inspections/schemas.py
  - apps/api/aip/modules/inspections/repository.py
  - apps/api/aip/modules/inspections/itp_rules.py
  - apps/api/aip/modules/inspections/itp.py
  - apps/api/aip/modules/inspections/signoff_chain.py
  - apps/api/aip/modules/inspections/workflow.py
  - apps/api/aip/modules/inspections/events.py
  - apps/api/aip/modules/inspections/routes.py
  - apps/api/aip/modules/inspections/api.py
  - apps/api/aip/modules/inspections/manifest.toml
  - apps/api/aip/modules/inspections/tests/test_itp_unit.py
  - apps/api/aip/modules/inspections/tests/test_itp_db.py
  - config/workflows/inspection.standard.json
  - config/terms/en-AU/inspections.json
- **steps**:
  - 1. Migration `<timestamp>_inspections_itp_signoffs.py`, one revision:
    - Create `itp_steps` with `render_template("tenant_table", table="itp_steps", sync=True, columns=...)`: `inspection_id uuid NOT NULL`, `asset_id uuid NOT NULL` (copied from the ITP), `seq integer NOT NULL CHECK (seq >= 1)`, `title text NOT NULL` (1–200 chars), `point_type text NOT NULL CHECK (point_type IN ('hold', 'witness', 'review', 'surveillance'))`, `acceptance_criteria text NULL`, `task_id uuid NULL`, `blocks_task_id uuid NULL` (scope tasks, plain uuids: scope_work links them in SCOPEWORK-03), `child_inspection_id uuid NULL`, `status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'ready', 'in_progress', 'released', 'waived', 'rejected'))`, `hold_flag_issue_id uuid NULL` (an issues NCR, plain uuid), `notice_hours integer NULL CHECK (notice_hours BETWEEN 0 AND 720)` (witness only, a CHECK), `ready_at timestamptz NULL`, `released_at timestamptz NULL`. Foreign keys `(inspection_id, tenant_id)` and `(child_inspection_id, tenant_id)` → `inspections (id, tenant_id)`; `UNIQUE (id, tenant_id)`; unique index `(tenant_id, inspection_id, seq) WHERE deleted_at IS NULL`; indexes `(tenant_id, task_id)`, `(tenant_id, blocks_task_id) WHERE point_type = 'hold'`, `(tenant_id, asset_id)`.
    - Create `inspection_signoffs` by hand, append-only like `workflow_decision_history`: `id`, `tenant_id`, `inspection_id`, `itp_step_id uuid NULL`, `asset_id`, `seq integer NOT NULL` with `UNIQUE (inspection_id, seq)`, `signatory_role text CHECK (signatory_role IN ('inspector', 'supervisor', 'third_party'))` (no `client` until OPEN-QUESTIONS #42 is answered; INSPECTIONS-05 widens it), `signer_user_id uuid NOT NULL`, `decision text CHECK (decision IN ('approve', 'reject', 'witnessed', 'waived'))`, `action_code text NOT NULL` (the assurance action checked), `status text CHECK (status IN ('applied', 'pending_countersign'))`, `countersigns_id uuid NULL`, `auth_strength text CHECK (auth_strength IN ('password', 'mfa', 'pin'))`, `assurance_level smallint CHECK (assurance_level IN (1, 2))`, `assurance_method text`, `authenticated_at timestamptz NULL`, `device_id uuid NULL`, `eligibility_result jsonb NULL` (always NULL until INSPECTIONS-07), `content_hash`, `prev_hash`, `entry_hash` (each `CHECK (... ~ '^[0-9a-f]{64}$')`), `comment text NULL` (≤ 2000), `signed_at timestamptz NOT NULL`, `created_at timestamptz NOT NULL DEFAULT now()`. No `updated_at`/`deleted_at`; FORCE RLS with the fail-closed tenant policy; `GRANT SELECT, INSERT` to `aip_app`, `SELECT` to `aip_readonly`, `REVOKE UPDATE, DELETE, TRUNCATE` from `aip_app`, `aip_jobs`, `aip_readonly`. Not range-partitioned, for the ADR 0031 reason (`UNIQUE (inspection_id, seq)` needs no partition key); so it is not listed in `partition_settings`. Indexes per the data model: `(tenant_id, inspection_id, signed_at)`, `(tenant_id, signer_user_id)`, `(tenant_id, asset_id)`.
  - 2. `itp_rules.py` (pure, no I/O): the step machine as data, with stable codes.
    - Actions: `ready` pending→ready (sets `ready_at`; for a witness point this is when notice is given); `start` ready→in_progress; `reopen` rejected→in_progress.
    - Sign-off decisions: `approve` in_progress→released (hold, review, surveillance); `witnessed` in_progress→released (witness only); `waived` ready|in_progress→waived (witness only, only when `now ≥ ready_at + notice_hours`, comment required); `reject` in_progress→rejected (comment required).
    - Assurance action per decision: hold `approve` → `hold_point.release`; `witnessed` → `witness.countersign`; review/surveillance `approve` and `waived` → `itp.signoff`; `reject` is not critical (assurance is still recorded).
    - `start` is refused while any lower-`seq` hold step is not `released`/`waived` (`BLOCKED_BY_HOLD`); `approve`/`witnessed`/`waived` are refused while `hold_flag_issue_id` is set (`STEP_ON_HOLD`).
  - 3. `signoff_chain.py`: `entry_hash(entry)` is sha256 (hex) of the RFC 8785 canonical JSON (the `rfc8785` library approvals and audit use) of every stored column except `entry_hash` and `created_at`; genesis `prev_hash = sha256("genesis:" + inspection_id)`; `verify_chain(entries)` → ok, or broken at `seq`. `content_hash` is sha256 of canonical `{inspectionId, templateRevisionId, stepId, answers}` where `answers` maps each field key to its current value from `InspectionsApi.get_current_responses`.
  - 4. `itp.py` `ItpService`, each call in one `with_tenant` transaction:
    - `create_steps(conn, policy, actor, inspection_id, steps)` (`itp.manage`): the inspection must be kind `itp` (422 `NOT_AN_ITP`) and in `draft`, `assignable` or `assigned` (409 `ITP_LOCKED`); a duplicate `seq` → 409 `DUPLICATE_SEQ`; `noticeHours` on a non-witness step → 422. Editing or deleting steps is out of scope.
    - `act(conn, policy, actor, step_id, action, expected_sync_version)` for `ready`/`start`/`reopen` (`itp.manage` for `ready`, `itp.sign` otherwise): lock the step and its ITP (`FOR UPDATE`); `start` needs the ITP in `in_progress` (409 `ITP_NOT_IN_PROGRESS`); apply through `aip.platform.db.concurrency.update_with_version` (stale version → 409 with the current row).
    - `sign(conn, policy, actor, step_id, decision, signatory_role, comment, expected_sync_version)` (`itp.sign`; `itp.waive` for `waived`): lock; check the rule (409 `INVALID_STEP_ACTION`, `BLOCKED_BY_HOLD`, `STEP_ON_HOLD`, `NOTICE_NOT_ELAPSED`; 422 `COMMENT_REQUIRED`); then, for a critical decision, build `SignoffContext(session=actor.session, aal2_available=<session aal 2 or identity's mfa_enrolled_at(conn, user) set>, now=..., step_up_url=...)` exactly as approvals does (ADR 0035 §4) and call `aip.modules.identity.api.check_signoff_assurance(conn, ctx, action_code)`:
      - `step_up_required` → raise identity's `StepUpRequiredError` (401 `STEP_UP_REQUIRED` with the step-up URL); nothing written.
      - `countersign_required` → append a `pending_countersign` signoff, leave the step unchanged, bump the step's `sync_version`, return 202.
      - `allow` → append an `applied` signoff and move the step.
      - While a pending signoff waits on the step, only the same decision is accepted (409 `COUNTERSIGN_PENDING`), never from its signer (409 `SELF_COUNTERSIGN`); the countersigner needs `itp.sign` and an `allow` (otherwise 401 step-up or 403 `COUNTERSIGN_ASSURANCE_REQUIRED`), and their `applied` row carries `countersigns_id`. Rows are never updated.
      - Every signoff stores `derive_assurance(session)` (level, method, `authenticated_at`, device), `auth_strength` mapped from the method (`password`, `pin` for `device_pin`, else `mfa`), `content_hash`, the chained hashes, `signed_at` (UTC) and `eligibility_result = NULL`. `signatoryRole: "client"` → 422 (`CLIENT_SIGNOFF_NOT_AVAILABLE`, OPEN-QUESTIONS #42).
    - When a step becomes `released` or `waived`: set `released_at` and `emit(conn, "itp_step.released", 1, {stepId, inspectionId, assetId, projectId, pointType, decision, taskId, blocksTaskId, releasedAt})`.
    - `place_hold(conn, step_id, *, issue_id)` and `clear_hold(conn, step_id, *, issue_id)` (no policy argument: the caller, issues, has authorised its NCR): a hold on a `released`/`waived` step → `StepAlreadyReleasedError`; a second hold by a different issue → `StepAlreadyHeldError`; clearing with another issue's id → `HoldMismatchError` (all 409 when surfaced over HTTP); each change emits `itp_step.hold_changed` v1 `{stepId, inspectionId, issueId, held}`.
  - 5. Guard facts and preset: the `inspection` facts provider in `workflow.py` adds `openStepCount` (live steps not `released`/`waived`; 0 for non-ITP kinds) and `heldStepCount`. In `config/workflows/inspection.standard.json` the `submit` guard becomes `{"and":[{"==":[{"var":"record.missingRequiredCount"},0]},{"==":[{"var":"record.openStepCount"},0]}]}` with `guardMessageKey: "inspection.guard.not_ready_to_submit"`, so an ITP cannot be submitted with open steps.
  - 6. Routes (strict bodies, camelCase, 422 validation; another tenant's inspection or step → 404 first; permissions checked in the service on the ITP's project):
    - `POST /api/v1/inspections/{id}/itp-steps {steps: [{seq, title, pointType, acceptanceCriteria?, taskId?, blocksTaskId?, noticeHours?}]}` → 201;
    - `GET /api/v1/inspections/{id}/itp-steps` (`inspection.view`) → steps in `seq` order with `status`, `held`, `releasedAt` and `availableActions` for the caller;
    - `POST /api/v1/itp-steps/{stepId}/actions {action, expectedSyncVersion?}`;
    - `POST /api/v1/itp-steps/{stepId}/signoffs {decision, signatoryRole, comment?, expectedSyncVersion?}` → 200 applied, 202 pending countersign;
    - `GET /api/v1/inspections/{id}/signoffs` (`inspection.view`) → entries (with assurance level, method and `status`) plus `chainValid`.
  - 7. `api.py` adds `InspectionsApi.get_itp_step(conn, step_id) -> ItpStepOut | None`, `is_step_released(conn, step_id) -> bool` (true only when `released` or `waived` and no hold flag; false for an unknown step), `place_hold` and `clear_hold`, and exports the three hold errors. Manifest: `permission_namespaces` gains `itp`; permissions `itp.manage` ("Set up ITP steps"), `itp.sign` ("Sign ITP steps: release holds, witness, reject"), `itp.waive` ("Waive a witness point after its notice period"); `[[events]]` `itp_step.released` v1 and `itp_step.hold_changed` v1.
  - 8. Terms: `itp.action.<code>`, `itp.decision.<code>`, `itp.signatory_role.<code>`, the error keys of steps 4 and 6 and `inspection.guard.not_ready_to_submit` in `config/terms/en-AU/inspections.json` (the point-type and step-status keys already exist).
- **Out of scope**: the eligibility check before signing (INSPECTIONS-07; `eligibility_result` stays NULL); client sign-off, the portal and multi-party sign-off chips (INSPECTIONS-05, blocked on OPEN-QUESTIONS #42); witness notice reminders and bookings; creating a child inspection per step (the column exists); hold scenarios on CUI data (INSPECTIONS-06); blocking scope tasks (SCOPEWORK-03 reads `is_step_released`); offline provisional release (after R1, ADR 0010 part 3).
- **acceptance**:
  - A later step cannot start while an earlier hold point is unreleased; a step with an NCR hold cannot be released.
  - Every release, witness, waiver and rejection is one `inspection_signoffs` row with the signer, decision, assurance level and method, content hash and chained hash; rows cannot be changed or removed, and `GET /signoffs` reports `chainValid`.
  - A critical sign-off below the tenant's minimum assurance either asks for step-up (nothing written) or is recorded as `pending_countersign` and has no effect until a different, sufficiently assured user countersigns.
  - `itp_step.released` v1 is emitted in the same transaction as each release or waiver; `is_step_released` answers other modules without them reading inspections tables.
  - An ITP with open steps cannot be submitted.
- **tests**:
  - **unit** (`test_itp_unit.py`):
    - Rule table: (`hold`, `in_progress`, `approve`) → `released`, action code `hold_point.release`; (`witness`, `in_progress`, `approve`) → `INVALID_STEP_ACTION`; (`review`, `in_progress`, `witnessed`) → `INVALID_STEP_ACTION`; (`witness`, `ready`, `waived`, ready 25 h ago, notice 24 h) → `waived`; the same at 23 h → `NOTICE_NOT_ELAPSED`; (`hold`, `in_progress`, `approve`, hold flag set) → `STEP_ON_HOLD`; `reject` without comment → `COMMENT_REQUIRED`.
    - Steps `[1 hold released, 2 hold in_progress, 3 review ready]`: `start` step 3 → `BLOCKED_BY_HOLD`; after step 2 is released → allowed.
    - `entry_hash` with keys reordered → same hash; changing `comment` `"ok"` → `"ok."` → different hash; `verify_chain` with entry 2's `decision` altered → broken at seq 2; empty chain → ok.
    - `signatoryRole: "client"` → validation error; an unknown body key `{"decision":"approve","signatoryRole":"inspector","assuranceLevel":2}` → validation error.
  - **integration** (`test_itp_db.py`, testcontainers-python Postgres, `kaefer-demo` and `tenant-b`; the INSPECTIONS-01/-02 conftest; ITP `ITP-101` (kind `itp`) on asset `TK-101` in project `KF-01` with steps 1 `hold` "Surface preparation", 2 `witness` "DFT check" (`noticeHours: 24`), 3 `review` "Final coat"; the ITP moved to `in_progress`; users inspector (`itp.sign`), supervisor (`itp.sign`, `itp.manage`, `itp.waive`), viewer):
    - Inspector with a fresh aal 2 session: `ready`, `start` and `approve` step 1 → 200, step 1 `released`; 1 `inspection_signoffs` row with `action_code = 'hold_point.release'`, `assurance_level = 2`, `seq = 1`, `prev_hash = sha256('genesis:'+id)`; 1 `domain_events` row named `itp_step.released`; `InspectionsApi.is_step_released(step1)` → true.
    - `start` step 3 while step 1 is unreleased → 409 `BLOCKED_BY_HOLD` and nothing written.
    - Inspector with an aal 1 password session and MFA enrolled, `approve` step 1 → 401 `STEP_UP_REQUIRED`; 0 new `inspection_signoffs` rows; step still `in_progress`.
    - Inspector with aal 1 and no aal 2 method available → 202; 1 `inspection_signoffs` row with `status = 'pending_countersign'`; step still `in_progress`; no `domain_events` row for `itp_step.released`. The same inspector signs again → 409 `SELF_COUNTERSIGN`. A supervisor `reject` → 409 `COUNTERSIGN_PENDING`. The supervisor with a fresh aal 2 session `approve` → 200; second row `applied` with `countersigns_id` = the pending row; step `released`; `GET /signoffs` → 2 entries, `chainValid: true`.
    - Witness: `waive` step 2 by the supervisor 1 hour after `ready` → 409 `NOTICE_NOT_ELAPSED`; with `ready_at` set 25 hours back by the fixture and comment "Client did not attend" → 200, status `waived`, signoff `decision = 'waived'`; inspector without `itp.waive` → 403.
    - `InspectionsApi.place_hold(step3, issue_id=N1)` → `approve` step 3 → 409 `STEP_ON_HOLD`; `is_step_released(step3)` → false; `clear_hold(step3, issue_id=N2)` → `HoldMismatchError`; `clear_hold(step3, issue_id=N1)` then `approve` → 200. 2 `domain_events` rows named `itp_step.hold_changed`.
    - `submit` on the ITP with step 3 open → 422 `GUARD_FAILED` with `messageKey: "inspection.guard.not_ready_to_submit"`; once all steps are `released`/`waived` (and required answers given) → 200.
    - `POST /inspections/{non-ITP id}/itp-steps` → 422 `NOT_AN_ITP`; on an ITP in `in_progress` → 409 `ITP_LOCKED`; two steps with `seq: 1` → 409 `DUPLICATE_SEQ`.
    - A stale `expectedSyncVersion` on `start` → 409 with the current step.
    - As `aip_app`: `UPDATE inspection_signoffs SET comment = 'x'` → permission denied; `DELETE FROM inspection_signoffs` → permission denied. As the owner role, alter one row's `comment` → `GET /signoffs` reports `chainValid: false`.
    - Viewer `POST /itp-steps/{id}/signoffs` → 403 and nothing written.
    - A `tenant-b` user: `GET /api/v1/inspections/{kaefer ITP}/itp-steps` → 404, `POST /api/v1/itp-steps/{kaefer step}/signoffs` → 404; `InspectionsApi.get_itp_step` on a `tenant-b` connection → None; as `aip_app` bound to `tenant-b`, `SELECT count(*) FROM itp_steps` → 0.
  - **e2e**:
    - API-only task: covered by the in-process HTTP integration tests above (as ADR 0035 §9; the step-up redirect itself is IDENTITY-04's journey). The ITP progress timeline page, with its Playwright journey, cross-tenant check and axe check, needs a page row: INSPECTIONS-04 does not depend on this task.
