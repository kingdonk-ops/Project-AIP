# ELIGIBILITY-02 — Eligibility check: hard block on expired, superseded or revoked certificates, results stored

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`eligibility`](../../docs/blueprint/modules/eligibility/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | ELIGIBILITY-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/eligibility/README.md`](../../docs/blueprint/modules/eligibility/README.md) and, only for
   columns, [`data-model.md`](../../docs/blueprint/modules/eligibility/data-model.md) (`eligibility_checks`)
3. [`ELIGIBILITY-01.md`](ELIGIBILITY-01.md) (tables, `expiry.py`, `status_changed_at`)
4. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (append-only evidence tables),
   [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox in the same transaction),
   [0025](../../docs/adr/0025-time-and-timezones.md) (calendar-day expiry in UTC),
   [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)
5. `db/templates/append_only_table.sql.tpl` and the `partition_settings` registration in
   `apps/api/migrations/versions/202610141000_append_only_grants.py`

## Spec

Publish one eligibility check that answers whether a person or asset holds every required certificate type at a given instant, hard-blocks on missing, expired, not-yet-valid, superseded or revoked certificates, and stores every answer as append-only evidence that sign-offs can reference (tag: extend).

> Other modules (INSPECTIONS-07 at step sign-off, SCOPEWORK later) call only
> `aip.modules.eligibility.api.EligibilityApi.check` on their own `with_tenant` connection, so the stored check
> commits or rolls back with their sign-off, and they stamp the returned `check_id` on it ("validity at time of
> use"). Nobody reads `certificates` directly.

- **files**:
  - apps/api/migrations/versions/<timestamp>_eligibility_checks.py
  - apps/api/aip/modules/eligibility/manifest.toml
  - apps/api/aip/modules/eligibility/tables.py
  - apps/api/aip/modules/eligibility/check.py
  - apps/api/aip/modules/eligibility/schemas.py
  - apps/api/aip/modules/eligibility/repository.py
  - apps/api/aip/modules/eligibility/service.py
  - apps/api/aip/modules/eligibility/events.py
  - apps/api/aip/modules/eligibility/routes.py
  - apps/api/aip/modules/eligibility/api.py
  - apps/api/aip/modules/eligibility/tests/test_check_unit.py
  - apps/api/aip/modules/eligibility/tests/test_check_db.py
  - config/terms/en-AU/eligibility.json
- **steps**:
  - 1. Migration `<timestamp>_eligibility_checks.py`: create `eligibility_checks` with
    `render_template("append_only_table", table="eligibility_checks", columns=..., partition_column="created_at")`
    and register it with `INSERT INTO partition_settings (table_name) VALUES ('eligibility_checks')` in the same
    revision. Columns: `subject_kind text NOT NULL` (`CHECK (subject_kind IN ('person','asset'))`),
    `subject_id uuid NOT NULL`, `requirement jsonb NOT NULL` (the required type codes as asked),
    `context_kind text NULL`, `context_id uuid NULL`, `asset_id uuid NULL`, `result text NOT NULL`
    (`CHECK (result IN ('eligible','blocked','overridden'))`; `overridden` is written from ELIGIBILITY-03),
    `reasons jsonb NOT NULL`, `checked_at timestamptz NOT NULL` (the instant asked about), `actor_id uuid NULL`;
    `CHECK ((context_kind IS NULL) = (context_id IS NULL))`; indexes `(tenant_id, subject_kind, subject_id,
    checked_at)` and `(tenant_id, context_kind, context_id)`. The template revokes UPDATE, DELETE and TRUNCATE.
  - 2. `check.py` (pure, no I/O) — reason codes are stable constants:
    `OK`, `CERT_MISSING`, `CERT_EXPIRED`, `CERT_NOT_YET_VALID`, `CERT_SUPERSEDED`, `CERT_REVOKED`, `TYPE_UNKNOWN`,
    `TYPE_OWNER_MISMATCH`, `SUBJECT_NOT_FOUND`.
    - Enforcement (owner answer #44, [ADR 0039](../../docs/adr/0039-owner-answers-item-types-witness-root-cause.md)): each `Reason` carries the type's `enforcement` and
      `blocking: bool`. A non-`OK` reason blocks only when the type is `hard_stop`; for `notify` it is recorded
      with `blocking: false` (the warning ELIGIBILITY-05 and INSPECTIONS-07 show); for `ignore` the type is not
      evaluated and returns `OK` with `enforcement: "ignore"`. `TYPE_UNKNOWN`, `TYPE_OWNER_MISMATCH` and
      `SUBJECT_NOT_FOUND` always block.
    - `state_at(cert, at) -> str`: the certificate's state at `at`, using ELIGIBILITY-01's `status_changed_at` so
      history answers correctly: `revoked`/`superseded` only if `status_changed_at <= at`; otherwise `expired` when
      `utc_date(at) > expires_on`; `not_yet_valid` when `utc_date(at) < issued_on`; else `valid`. Dates use
      `aip.modules.eligibility.expiry.utc_date` (ADR 0025: valid through 23:59:59 UTC on `expires_on`).
    - `decide(type_code, type_row, candidates, at) -> Reason`: `type_row is None` → `TYPE_UNKNOWN`; any candidate
      `valid` at `at` → `OK` with that certificate (the one expiring last; no expiry beats any date) and its
      `expiryStatus` (green or amber); otherwise the first match in the priority `CERT_EXPIRED`,
      `CERT_NOT_YET_VALID`, `CERT_REVOKED`, `CERT_SUPERSEDED`, naming the newest such certificate; no candidates →
      `CERT_MISSING`. Fail closed: an unexpected state is a block, never `OK`.
    - `Reason` = `{typeCode, code, certificateId?, expiresOn?, expiryStatus?, messageKey}` where `messageKey` is
      `eligibility.reason.<code lower-case>`.
  - 3. `service.check(conn, *, subject_kind, subject_id, requirement, at, context=None, actor_id=None)`:
    - `at` must be timezone-aware (naive → `ValueError`); `requirement.certificate_type_codes` is 1–20 distinct codes.
    - The subject must exist in the bound tenant (`aip.modules.identity.api.get_user` /
      `aip.modules.assets.api.AssetsApi.assert_asset_exists`); if not, every reason is `SUBJECT_NOT_FOUND`.
    - Load the types by code (ignoring case) and the subject's non-deleted certificates of those types in **one**
      query (no N+1); a type whose `owner_kind` differs from `subject_kind` → `TYPE_OWNER_MISMATCH`.
    - `result = 'eligible'` when no reason has `blocking: true`, else `'blocked'`. Insert one `eligibility_checks` row
      (UUIDv7 id, `checked_at = at`) on the caller's connection and return
      `EligibilityResult(eligible, result, reasons, check_id, checked_at)`.
    - On `blocked`, emit `eligibility.blocked` v1 with `aip.platform.events.outbox.emit` in the same transaction:
      `{checkId, subjectKind, subjectId, contextKind, contextId, reasonCodes}` (ids and codes only, no names).
    - Leave one seam for ELIGIBILITY-03: a function `apply_overrides(conn, reasons, ...)` that returns the reasons
      unchanged in this task.
  - 4. `api.py`: `EligibilityApi.check(conn, *, subject_kind, subject_id, requirement, at, context=None,
    actor_id=None) -> EligibilityResult`, plus the models `Requirement(certificate_type_codes: list[str])`,
    `CheckContext(context_kind: str, context_id: UUID, asset_id: UUID | None = None)` and `EligibilityResult`;
    `EligibilityApi.get_check(conn, check_id)` for sign-off pages that show the stored evidence.
  - 5. Manifest: add `eligibility` to `permission_namespaces`; permissions `eligibility.view` (read stored checks)
    and `eligibility.check` (run a check from the API); `[[events]]` `eligibility.blocked` v1.
  - 6. Routes under `/api/v1/eligibility` with `requires(...)` and strict bodies (unknown key → 422):
    - `POST /checks {subjectKind, subjectId, certificateTypeCodes, contextKind?, contextId?}` (`eligibility.check`)
      → 201 with the result. The instant is always the server's `now()` in UTC: the HTTP API cannot store evidence
      for another time. `actor_id` is the caller.
    - `GET /checks/{id}` (`eligibility.view`) → the stored row; another tenant's id → 404.
    - `GET /checks?subjectKind=&subjectId=` (`eligibility.view`) → newest first, keyset paging, limit ≤ 100.
  - 7. Terms: `eligibility.reason.*` for every reason code, `eligibility.result.eligible|blocked|overridden`.
- **acceptance**:
  - One call answers for all required types and writes exactly one `eligibility_checks` row, on the caller's
    transaction; a rollback by the caller leaves no row and no event.
  - Expired, not-yet-valid, superseded, revoked or missing certificates block for `hard_stop` types, warn without
    blocking for `notify` types and are skipped for `ignore` types; nothing passes on an error.
  - A check at a past instant answers as of that instant (a certificate revoked later still counted as valid then).
  - Stored checks cannot be updated or deleted by `aip_app`.
  - Other modules use only `EligibilityApi`; the import contracts test (`apps/api/tests/arch/test_import_contracts.py`) still passes.
- **tests**:
  - **unit** (`test_check_unit.py`, no database; `at = 2026-10-31T12:00Z` unless stated):
    - One valid certificate expiring 2026-12-31 → `OK`, `expiryStatus: "green"`.
    - Expiring 2026-11-10 (amber at 30 days) → `OK`, `expiryStatus: "amber"` (amber warns, never blocks).
    - Same expired certificate on a `notify` type → `CERT_EXPIRED`, `blocking: false`, result `eligible`; on an
      `ignore` type → `OK`, `enforcement: "ignore"`.
    - Expiring 2026-10-30 → `CERT_EXPIRED`. Expiring 2026-10-31 at `2026-10-31T23:59:59Z` → `OK`; at
      `2026-11-01T00:00:00Z` → `CERT_EXPIRED`.
    - `issued_on = 2026-11-01` → `CERT_NOT_YET_VALID`.
    - Status `revoked` with `status_changed_at = 2026-10-20T00:00Z` → `CERT_REVOKED`; the same certificate checked at
      `2026-10-15T00:00Z` → `OK`.
    - Only a `superseded` certificate (changed 2026-10-01) → `CERT_SUPERSEDED`; superseded plus its valid
      replacement → `OK` naming the replacement.
    - One expired and one revoked → `CERT_EXPIRED` (priority). No certificates → `CERT_MISSING`.
    - `type_row = None` → `TYPE_UNKNOWN`. A naive `at` → `ValueError`.
  - **integration** (`test_check_db.py`, testcontainers-python Postgres, tenants `kaefer-demo` and `tenant-b`;
    types `CSWIP-3.1` and `CONFINED-SPACE` for people and `CAL-UT` for assets from ELIGIBILITY-01's API):
    - alice holds a valid `CSWIP-3.1` (expires UTC today + 60) and an expired `CONFINED-SPACE` (today − 1).
      `EligibilityApi.check(conn, subject_kind="person", subject_id=alice, requirement=Requirement(
      certificate_type_codes=["CSWIP-3.1","CONFINED-SPACE"]), at=now)` → `eligible: False`, `result: "blocked"`,
      reasons `[OK, CERT_EXPIRED]`; `SELECT count(*) FROM eligibility_checks` → 1; `domain_events` has 1
      `eligibility.blocked` row.
    - The same check with only `["CSWIP-3.1"]` → `eligible: True`, 1 more check row, no new `eligibility.blocked`.
    - A UT gauge asset (`AssetsApi.create_asset`) with a `CAL-UT` certificate revoked through the ELIGIBILITY-01 API
      → `CERT_REVOKED`; checked with `at` = one hour before the revoke → `OK`.
    - `["NO-SUCH-TYPE"]` → `TYPE_UNKNOWN`, blocked. `CAL-UT` asked for a person → `TYPE_OWNER_MISMATCH`.
    - A subject id from `tenant-b` → `SUBJECT_NOT_FOUND`, blocked, and no `tenant-b` data in the reasons.
    - Caller rollback: run `check` inside `with_tenant`, then raise → 0 `eligibility_checks` rows and 0
      `eligibility.blocked` events.
    - Query count: a check for 5 types issues at most 3 SQL statements before the insert (types, certificates,
      subject).
    - `POST /api/v1/eligibility/checks` as a user with `eligibility.check` → 201 with `checkId`; without it → 403;
      body with `"at":"2020-01-01T00:00:00Z"` → 422 (unknown key); `GET /checks/{id}` as `tenant-b` → 404.
    - As `aip_app`: `UPDATE eligibility_checks SET result = 'eligible'` → `permission denied`; `DELETE` →
      `permission denied`.
    - After the dispatcher runs, `expect_audited(conn, "eligibility.blocked")` passes.
  - **e2e**:
    - API-only task with no Playwright API project yet: the HTTP journeys run in the integration suite against the
      real app and Postgres. The browser hard block at sign-off is INSPECTIONS-07's journey.

Out of scope: overrides (ELIGIBILITY-03); competency requirements per template, category or discipline, and crew or
work-package pre-checks (later rows: R1 callers pass the type codes they need); grace periods (OPEN-QUESTIONS #44).
