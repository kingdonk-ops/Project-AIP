# ELIGIBILITY-03 — Audited eligibility override with named permission, reason, approver and expiry

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`eligibility`](../../docs/blueprint/modules/eligibility/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | AUDIT-01, ELIGIBILITY-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/eligibility/README.md`](../../docs/blueprint/modules/eligibility/README.md) and, only for
   columns, [`data-model.md`](../../docs/blueprint/modules/eligibility/data-model.md) (`eligibility_overrides`)
3. [`ELIGIBILITY-02.md`](ELIGIBILITY-02.md) (`check.py` reason codes, the `apply_overrides` seam)
4. ADRs: [0010](../../docs/adr/0010-signoff-assurance.md) (sign-off assurance),
   [0034](../../docs/adr/0034-invites-and-step-up-implementation.md) (401 `STEP_UP_REQUIRED`),
   [0035](../../docs/adr/0035-transition-service-implementation.md) (how approvals calls the assurance check),
   [0025](../../docs/adr/0025-time-and-timezones.md) (point-in-time expiry is a UTC instant),
   [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)
5. `apps/api/aip/modules/audit/api.py` (module docstring: how domain events reach `audit_log`) and
   `apps/api/tests/fixtures/audit.py` (`expect_audited`)

## Spec

Let a person with a named permission request a time-limited override of a hard eligibility block, with a reason, approved by a different person who holds a separate named permission and passes the sign-off assurance check, so the check reports `overridden` until the override expires or is revoked, with every step in the audit chain (tag: extend).

> **Audit path.** The audit entry goes through the audit module's published route. Each override state change
> emits a domain event with `aip.platform.events.outbox.emit` in the same transaction, and the AUDIT-02 outbox
> writer appends it to `audit_log` with `aip.modules.audit.api.AuditApi.append`. The `AuditApi` docstring says
> modules never call `append` themselves, because it opens its own `aip_audit_writer` transaction and would commit
> even when the override rolls back. Do not call `append` from this module. Do not call `record_security_event`
> either: that is for actions that have no domain event.

- **files**:
  - apps/api/migrations/versions/<timestamp>_eligibility_overrides.py
  - apps/api/aip/modules/eligibility/manifest.toml
  - apps/api/aip/modules/eligibility/tables.py
  - apps/api/aip/modules/eligibility/overrides.py
  - apps/api/aip/modules/eligibility/policies.py
  - apps/api/aip/modules/eligibility/schemas.py
  - apps/api/aip/modules/eligibility/repository.py
  - apps/api/aip/modules/eligibility/service.py
  - apps/api/aip/modules/eligibility/events.py
  - apps/api/aip/modules/eligibility/routes.py
  - apps/api/aip/modules/eligibility/api.py
  - apps/api/aip/modules/eligibility/tests/test_overrides_unit.py
  - apps/api/aip/modules/eligibility/tests/test_overrides_db.py
  - config/terms/en-AU/eligibility.json
- **steps**:
  - 1. Migration `<timestamp>_eligibility_overrides.py`: create `eligibility_overrides` from
    `render_template("tenant_table", ...)`, then `REVOKE DELETE ON eligibility_overrides FROM aip_app` (rows are
    never removed; a withdrawn override is `revoked`). Columns: `subject_kind text NOT NULL`
    (`'person'|'asset'`), `subject_id uuid NOT NULL`, `certificate_type_id uuid NOT NULL` (FK
    `(certificate_type_id, tenant_id) → certificate_types (id, tenant_id)`), `certificate_id uuid NULL` (the
    blocking certificate, FK `(certificate_id, tenant_id) → certificates (id, tenant_id)`),
    `blocked_code text NOT NULL` (the reason code being overridden), `context_kind text NULL`, `context_id uuid NULL`,
    `asset_id uuid NULL`, `check_id uuid NULL` (the blocked check that led to the request; no FK, as
    `eligibility_checks` is partitioned), `reason text NOT NULL` (`CHECK (char_length(btrim(reason)) BETWEEN 10 AND
    2000)`), `status text NOT NULL DEFAULT 'requested'`
    (`CHECK (status IN ('requested','approved','rejected','revoked'))`), `requested_by uuid NOT NULL`,
    `valid_until timestamptz NOT NULL`, `decided_by uuid NULL`, `decided_at timestamptz NULL`,
    `decision_comment text NULL`, `approver_assurance jsonb NULL`, `revoked_by uuid NULL`,
    `revoked_at timestamptz NULL`, `revoke_reason text NULL`, `sync_version integer NOT NULL DEFAULT 1`. Checks:
    `decided_by IS NULL OR decided_by <> requested_by`; `(status = 'requested') = (decided_by IS NULL)`;
    `(status = 'revoked') = (revoked_at IS NOT NULL)`; `(context_kind IS NULL) = (context_id IS NULL)`. Indexes:
    `(tenant_id, subject_kind, subject_id, certificate_type_id) WHERE status IN ('approved','revoked')` and
    `(tenant_id, status, created_at)`. There is no stored `expired`: it is computed (step 3).
  - 2. Manifest: permissions `eligibility.override.request` ("Request an eligibility override") and
    `eligibility.override.approve` ("Approve, reject or revoke eligibility overrides", `privileged = true`);
    reading uses `eligibility.view`. `[[events]]` v1: `eligibility.override_requested`,
    `eligibility.override_approved`, `eligibility.override_rejected`, `eligibility.override_revoked`,
    `eligibility.override_used`. Payloads hold ids, codes and instants only:
    `{overrideId, subjectKind, subjectId, certificateTypeId, blockedCode, contextKind, contextId, validUntil,
    requestedBy, decidedBy?}`. The free-text reason stays in the table. The event is the audit record, and the
    audit row links to the override by `record_id`.
  - 3. `overrides.py` (pure):
    - `OVERRIDABLE = {CERT_EXPIRED, CERT_MISSING, CERT_NOT_YET_VALID, CERT_SUPERSEDED}`. `CERT_REVOKED`,
      `TYPE_UNKNOWN`, `TYPE_OWNER_MISMATCH` and `SUBJECT_NOT_FOUND` can never be overridden: a revocation is a
      deliberate decision, and the others are data errors.
    - `MAX_OVERRIDE_DAYS = 14` (in `policies.py`): `valid_until` must be after `now` and no later than
      `created_at + 14 days`.
    - `is_effective(row, at)`: `status IN ('approved','revoked')` and `decided_at <= at < valid_until` and
      (`revoked_at IS NULL` or `at < revoked_at`). This is point-in-time, so a past check still answers as it did then.
    - `display_status(row, now)`: `expired` when `approved` and `valid_until <= now`, else `status`. Computed in
      the query too, so the list can filter on it.
    - `matches(row, type_id, context)`: an override with no context covers any context; one with a context covers
      only that `(context_kind, context_id)`.
  - 4. Service, each a single `with_tenant` transaction that emits its event:
    - **Request** (`eligibility.override.request`): `{subjectKind, subjectId, certificateTypeCode, reason,
      validUntil, contextKind?, contextId?, assetId?, checkId?}`. Run ELIGIBILITY-02's pure `decide` for that one type
      at `now`, without storing a check. `OK` gives 409 `NOT_BLOCKED`. A code outside `OVERRIDABLE` gives 409
      `NOT_OVERRIDABLE` with the code. Otherwise store `blocked_code` and `certificate_id`. `validUntil` in the past
      or more than 14 days ahead gives 422 `OVERRIDE_WINDOW_INVALID`. A blank or short reason gives 422
      `REASON_REQUIRED`. Emit `eligibility.override_requested`.
    - **Approve** (`eligibility.override.approve`), body `{expectedSyncVersion, comment?, validUntil?}`. The
      approver may shorten the window, never extend it. Steps in order:
      - (a) Lock the row `FOR UPDATE`. Another tenant's id gives 404.
      - (b) The status must be `requested`, else 409 `INVALID_STATUS_TRANSITION`.
      - (c) The approver must not be the requester, else 409 `SELF_APPROVAL`.
      - (d) `valid_until > now`, else 409 `OVERRIDE_WINDOW_PASSED`.
      - (e) Run the sign-off assurance check with `aip.modules.identity.api.check_signoff_assurance(conn, ctx,
        "eligibility.override.approve")`. Build the `SignoffContext` the same way the approvals transition service
        does (ADR 0035): the session facts, plus `aal2_available` from the session's aal or
        `aip.modules.identity.api.mfa_enrolled_at`. `step_up_required` raises identity's `StepUpRequiredError`, which
        gives 401 `STEP_UP_REQUIRED`. `countersign_required` gives 403 `OVERRIDE_ASSURANCE_REQUIRED`: the approval
        is already the second person, so a provisional approval is not offered. `allow` continues.
      - (f) Set `approved`, `decided_by`, `decided_at = now()` and `approver_assurance` (the returned `Assurance`)
        with `aip.platform.db.concurrency.update_with_version`. A stale version gives 409.
      - (g) Emit `eligibility.override_approved`.

      Nothing is written before (a) to (e) all pass.
    - **Reject** (`eligibility.override.approve`, `comment` required): `requested` becomes `rejected`. The
      self-approval rule applies. Emit `eligibility.override_rejected`.
    - **Revoke** (`eligibility.override.approve`, `reason` required): `approved` becomes `revoked`, and `revoked_at
      = now()` takes effect at once. Emit `eligibility.override_revoked`. Revoking anything else gives 409
      `INVALID_STATUS_TRANSITION`.
  - 5. Fill ELIGIBILITY-02's `apply_overrides` seam inside `EligibilityApi.check`. Load the effective overrides
    for the subject and the blocked types in one query at `at`. Each blocked reason whose code is in `OVERRIDABLE`
    and has a matching effective override becomes `{typeCode, code: "OVERRIDDEN", underlyingCode, overrideId,
    overrideValidUntil, messageKey}`. If every non-`OK` reason is overridden, the result is `overridden` with
    `eligible: True`, and the check emits `eligibility.override_used` (`{checkId, overrideIds, subjectKind,
    subjectId, contextKind, contextId}`) instead of `eligibility.blocked`. A mix of overridden and still-blocked
    reasons stays `blocked`.
  - 6. Routes under `/api/v1/eligibility/overrides`, with `requires(...)` and strict bodies (an unknown key gives 422):
    - `POST /` (request)
    - `GET /` (`eligibility.view`), filtered by `status` (including the computed `expired`), `subjectKind`,
      `subjectId`, `requestedBy`, newest first, keyset paging
    - `GET /{id}`
    - `POST /{id}/approve`, `POST /{id}/reject`, `POST /{id}/revoke`

    Each response carries `displayStatus` and `validUntil` (RFC 3339, `Z`).
  - 7. Terms: `eligibility.override.*` labels and statuses (`requested`, `approved`, `rejected`, `revoked`,
    `expired`), and one message key per error code above.
- **acceptance**:
  - An override needs two different people, each holding a named permission. The approver must pass the sign-off
    assurance check. Every override has a reason and a UTC expiry no more than 14 days out.
  - Revoked certificates can never be overridden. An override covers only its subject, its certificate type and
    (when it has one) its context.
  - An effective override turns the check's result into `overridden` with the override id in the reasons. After
    `valid_until` or a revoke, the same check is `blocked` again with no write or job.
  - The request, decision, revoke and every use each produce one domain event in the same transaction. After the
    dispatcher runs, each is in `audit_log`. A rolled-back request leaves no event and no audit entry.
- **tests**:
  - **unit** (`test_overrides_unit.py`). The override was approved at `2026-10-20T00:00Z` with `valid_until =
    2026-10-27T00:00Z`:
    - `is_effective` at `2026-10-26T23:59:59Z` gives `True`. At `2026-10-27T00:00:00Z` it gives `False`
      (exclusive end). At `2026-10-19T23:59:59Z` it gives `False`.
    - With `revoked_at = 2026-10-22T00:00Z`: at `2026-10-21T00:00Z` it gives `True`, and at `2026-10-23T00:00Z` it
      gives `False`.
    - `display_status` of `approved` at `now = 2026-10-28` gives `expired`. A `requested` override gives
      `requested`.
    - `matches` with no context against any context gives `True`. A context of `(itp_step, X)` against
      `(itp_step, Y)` gives `False`.
    - `CERT_REVOKED in OVERRIDABLE` gives `False`. A window of 15 days gives `OVERRIDE_WINDOW_INVALID`.
  - **integration** (`test_overrides_db.py`). These use testcontainers-python Postgres and the tenants
    `kaefer-demo` and `tenant-b`. `alice` holds `eligibility.override.request`. `bob` holds
    `eligibility.override.approve` and signs in with a fresh aal2 stub session. The subject is the person `welder`
    (an `app_user` row in `kaefer-demo`), whose `CSWIP-3.1` certificate expired yesterday (UTC):
    - Alice POSTs an override with the reason "Renewal booked, inspector shortage this shift", `validUntil` = now
      + 2 days, and context `("itp_step", S)`. The answer is 201, `status: "requested"` and `blockedCode:
      "CERT_EXPIRED"`.
    - Alice approves her own request: 409 `SELF_APPROVAL`, and the row is still `requested`.
    - A user with only `eligibility.view` approves: 403, and nothing is written.
    - Bob approves: 200 with `status: "approved"`. `approver_assurance.level` is 2.
      `domain_events` has 1 `eligibility.override_approved` row.
    - `EligibilityApi.check` for the welder on `["CSWIP-3.1"]` with context `("itp_step", S)` gives `result:
      "overridden"`, `eligible: True`, `reasons[0].underlyingCode: "CERT_EXPIRED"` and the override id. The same
      check with context `("itp_step", T)` gives `blocked`.
    - The same check with `at` = `valid_until` + 1 second gives `blocked`.
    - Bob revokes with "Certificate not renewed". The next check gives `blocked`. A check with `at` = 1 minute
      before the revoke still gives `overridden`.
    - Bob has aal 1 and `mfa_enrolled_at` set: 401 `STEP_UP_REQUIRED`. Bob has aal 1 and is not enrolled: 403
      `OVERRIDE_ASSURANCE_REQUIRED`. Neither case writes a row change or an event.
    - Request on a certificate that was revoked through the ELIGIBILITY-01 API: 409 `NOT_OVERRIDABLE` with
      `CERT_REVOKED`. Request on a valid certificate: 409 `NOT_BLOCKED`.
    - `validUntil` = now + 15 days: 422 `OVERRIDE_WINDOW_INVALID`. A reason of `"ok"`: 422 `REASON_REQUIRED`.
    - Approve after `valid_until` has passed (seeded with a past window as the superuser): 409
      `OVERRIDE_WINDOW_PASSED`. `GET /overrides?status=expired` on an approved override past its window returns
      1 item.
    - Two concurrent approvals of one request with the same `expectedSyncVersion` give one 200 and one 409.
    - `tenant-b` runs `GET /overrides/{kaefer id}`: 404. `GET /overrides` returns 0 items.
    - As `aip_app`, `DELETE FROM eligibility_overrides` gives `permission denied`.
    - After the dispatcher runs, `expect_audited(conn, "eligibility.override_requested", record_id=<id>)` and the
      same for `_approved`, `_revoked` and `eligibility.override_used` all pass. A request whose transaction is
      rolled back leaves 0 `audit_log` rows for its id.
  - **e2e**:
    - This task is API-only and there is no Playwright API project yet, so the integration suite runs the
      two-person journey against the real app and Postgres. The override request queue page is not in this row
      (no board row yet; proposed to the PLAN-R1 lead).

Out of scope: running overrides as an approvals-engine workflow (a two-person rule is enough for R1); per-tenant
maximum durations (a constant of 14 days for now); the override queue page.
