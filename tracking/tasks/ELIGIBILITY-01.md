# ELIGIBILITY-01 — Certificate types and certificates with computed expiry status

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`eligibility`](../../docs/blueprint/modules/eligibility/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | ASSETS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/eligibility/README.md`](../../docs/blueprint/modules/eligibility/README.md) and, only for
   columns, [`data-model.md`](../../docs/blueprint/modules/eligibility/data-model.md) (`certificate_types`, `certificates`)
3. [`ASSETS-01.md`](ASSETS-01.md) (the `AssetsApi` this task calls)
4. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (SQLAlchemy Core, raw-SQL Alembic, `with_tenant`),
   [0004](../../docs/adr/0004-repository-layout.md) (only `api.py` crosses modules),
   [0025](../../docs/adr/0025-time-and-timezones.md) (calendar-day expiry in UTC),
   [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)
5. The pattern to copy: `apps/api/aip/modules/projects/` (tables, repository, service, routes, manifest, tests)

## Spec

Create the eligibility module with configurable certificate types and per-owner certificates (people and assets), whose green/amber/red expiry status is computed in the query from the UTC date and never stored (tag: extend).

> **Time zone.** The module README says "use AWST time zone handling". ADR 0025 point 5 (owner, 2026-10-13) overrides
> it and ADR 0036 records the outcome: a certificate is valid **through 23:59:59 UTC on `expires_on`**, compared with
> the UTC date. AWST appears only at presentation (ELIGIBILITY-04). Follow the ADR; the tests below pin the
> boundary in UTC and show what it means for a Perth user.

> **Owners in R1.** `owner_kind` is `person` (an `app_user` of the tenant) or `asset` (any register item from
> ASSETS-01; equipment and instruments are assets). Company, material batch and project owners are not in R1.

- **files**:
  - apps/api/migrations/versions/<timestamp>_eligibility_certificates.py
  - apps/api/aip/modules/eligibility/__init__.py
  - apps/api/aip/modules/eligibility/manifest.toml
  - apps/api/aip/modules/eligibility/tables.py
  - apps/api/aip/modules/eligibility/expiry.py
  - apps/api/aip/modules/eligibility/schemas.py
  - apps/api/aip/modules/eligibility/repository.py
  - apps/api/aip/modules/eligibility/service.py
  - apps/api/aip/modules/eligibility/policies.py
  - apps/api/aip/modules/eligibility/events.py
  - apps/api/aip/modules/eligibility/routes.py
  - apps/api/aip/modules/eligibility/api.py
  - apps/api/aip/modules/eligibility/tests/conftest.py
  - apps/api/aip/modules/eligibility/tests/test_expiry.py
  - apps/api/aip/modules/eligibility/tests/test_certificates_db.py
  - config/terms/en-AU/eligibility.json
- **steps**:
  - 1. Scaffold with `python tools/new_module.py eligibility`. In `manifest.toml`: `depends_on = ["tenancy",
    "identity", "assets"]`, `permission_namespaces = ["certificate"]` (ELIGIBILITY-02 adds `eligibility`), and the
    permissions `certificate.view`, `certificate.create`, `certificate.update`, `certificate.revoke`,
    `certificate.type.manage`. Declare `[[events]]` `certificate_type.created` v1, `certificate_type.updated` v1,
    `certificate.created` v1, `certificate.updated` v1, `certificate.superseded` v1, `certificate.revoked` v1.
  - 2. Migration `<timestamp>_eligibility_certificates.py`, both tables rendered with
    `render_template("tenant_table", ...)` (uuid PK, `tenant_id`, timestamps, `deleted_at`, FORCE RLS with the
    fail-closed policy, `aip_app` grants), then `REVOKE DELETE ... FROM aip_app` on both (soft delete only):
    - create `certificate_types` with `code text NOT NULL`, `name text NOT NULL`, `owner_kind text NOT NULL`
      (`CHECK (owner_kind IN ('person','asset'))`), `requires_expiry boolean NOT NULL DEFAULT true`,
      `amber_days integer NOT NULL DEFAULT 30` (`CHECK (amber_days BETWEEN 0 AND 365)`),
      `reminder_offsets jsonb NOT NULL DEFAULT '[60,30,7]'` (stored for ELIGIBILITY-05),
      `suppress_when_unavailable boolean NOT NULL DEFAULT false` (stored for ELIGIBILITY-05),
      `enforcement text NOT NULL DEFAULT 'hard_stop'` (`CHECK (enforcement IN ('ignore','notify','hard_stop'))`;
      owner answer #44, [ADR 0039](../../docs/adr/0039-owner-answers-item-types-witness-root-cause.md); read by ELIGIBILITY-02, settable on create and update),
      `sync_version integer NOT NULL DEFAULT 1`; `UNIQUE (id, tenant_id)`; unique index
      `(tenant_id, upper(code)) WHERE deleted_at IS NULL`.
    - create `certificates` with `certificate_type_id uuid NOT NULL`, `owner_kind text NOT NULL` (same check),
      `owner_id uuid NOT NULL`, `number text NULL`, `issuer text NULL`, `issued_on date NULL`,
      `expires_on date NULL`, `status text NOT NULL DEFAULT 'valid'`
      (`CHECK (status IN ('valid','superseded','revoked'))`), `status_changed_at timestamptz NULL`,
      `status_reason text NULL`, `superseded_by uuid NULL`, `document_file_id uuid NULL`,
      `sync_version integer NOT NULL DEFAULT 1`; `CHECK (expires_on IS NULL OR issued_on IS NULL OR expires_on >=
      issued_on)`; `CHECK ((status = 'superseded') = (superseded_by IS NOT NULL))`; FKs
      `(certificate_type_id, tenant_id) → certificate_types (id, tenant_id)` and
      `(superseded_by, tenant_id) → certificates (id, tenant_id)` (so nothing points across tenants); indexes
      `(tenant_id, owner_kind, owner_id) WHERE deleted_at IS NULL` and
      `(tenant_id, expires_on) WHERE status = 'valid' AND deleted_at IS NULL`.
    - `document_file_id` holds an uploads stored-file id. This task never sets it (the API returns it read-only);
      ELIGIBILITY-04 validates and sets it through `aip.modules.uploads.api.get_stored_file` (UPLOADS-08). No FK
      across modules.
    - No `expired` status and no RAG column: both are computed (step 3).
  - 3. `expiry.py` (pure, no I/O):
    - `utc_date(at: datetime) -> date`: raises `ValueError` for a naive datetime; otherwise `at.astimezone(UTC).date()`.
    - `expiry_status(expires_on: date | None, amber_days: int, at: datetime) -> tuple[str, int | None]`:
      `days = expires_on - utc_date(at)`; `None` expiry → `("none", None)`; `days < 0` → `red`;
      `days < amber_days` → `amber`; else `green`. A certificate expiring today is amber (or green when
      `amber_days = 0`), never red.
    - `expires_at_utc(expires_on) -> str`: `"<date>T23:59:59Z"`, the cutoff the UI shows (ADR 0025 point 5).
    - `validate_reminder_offsets(values)`: 1–6 distinct integers in 1..365, stored sorted descending.
  - 4. `repository.py`: SQLAlchemy Core on the connection from `with_tenant`. One SQL expression builds
    `expiry_status`, `days_to_expiry` and `display_status` from a bound `at` parameter
    (`(CAST(:at AS timestamptz) AT TIME ZONE 'UTC')::date`), so the list can filter and sort by them:
    `display_status` = `status` when not `valid`, else `expired` when the date is past, else `valid`. The SQL and
    `expiry.expiry_status` must agree on every row of the unit-test boundary table (an integration test checks it).
    List with keyset paging (the `aip.modules.projects` cursor pattern), filters `owner_kind`, `owner_id`,
    `certificate_type_id`, `status`, `expiry_status`, sort `expires_on` (nulls last) or `updated_at`.
  - 5. `service.py` (all writes in one `with_tenant` transaction, ids are UUIDv7 from the app, each write emits its
    event with `aip.platform.events.outbox.emit` in the same transaction):
    - Types: create, update (`update_with_version` from `aip.platform.db.concurrency`; changing `owner_kind` once
      certificates exist → 409 `TYPE_IN_USE`), soft delete (live certificates → 409 `TYPE_IN_USE`); a duplicate
      code ignoring case → 409 `DUPLICATE_CODE`.
    - Create certificate: the type must exist (422 `TYPE_NOT_FOUND`); `owner_kind` must equal the type's
      (422 `OWNER_KIND_MISMATCH`); the owner must exist in the caller's tenant — `person` through
      `aip.modules.identity.api.get_user(conn, owner_id)`, `asset` through
      `aip.modules.assets.api.AssetsApi.assert_asset_exists(conn, owner_id)` — else 422 `OWNER_NOT_FOUND` (the
      same answer for another tenant's id, so nothing leaks); a type with `requires_expiry` needs `expires_on`
      (422 `EXPIRY_REQUIRED`); `expires_on < issued_on` → 422 `INVALID_DATES`.
    - Update `number`, `issuer`, `issued_on`, `expires_on` on a `valid` certificate only, with
      `expectedSyncVersion` (mismatch → 409 with the current row).
    - Supersede: lock the old row `FOR UPDATE`; it must be `valid` (else 409 `INVALID_STATUS_TRANSITION`); insert
      the replacement (same type and owner, new number and dates); set the old row `status = 'superseded'`,
      `superseded_by`, `status_changed_at = now()`; emit `certificate.created` and `certificate.superseded`
      (`{certificateId, supersededBy, certificateTypeId, ownerKind, ownerId}`).
    - Revoke with a required `reason` (1–500 chars): `valid` → `revoked`, `status_changed_at`, `status_reason`;
      anything else → 409 `INVALID_STATUS_TRANSITION`.
    - `status_changed_at` is what ELIGIBILITY-02 uses to answer "was it valid at time t".
  - 6. `routes.py` under `/api/v1/eligibility`, every route with `requires(...)` from
    `aip.platform.access.dependencies` (deny by default), strict request models (`extra="forbid"`, camelCase
    aliases) so an unknown key is 422:
    - `GET/POST /certificate-types` (`certificate.view` / `certificate.type.manage`),
      `PATCH/DELETE /certificate-types/{id}` (`certificate.type.manage`)
    - `GET /certificates` and `GET /certificates/{id}` (`certificate.view`), `POST /certificates`
      (`certificate.create`), `PATCH /certificates/{id}` (`certificate.update`),
      `POST /certificates/{id}/supersede` (`certificate.create`), `POST /certificates/{id}/revoke`
      (`certificate.revoke`)
    - Responses carry `status`, `displayStatus`, `expiryStatus`, `daysToExpiry`, `expiresAtUtc` (step 3) and the
      type's `amberDays`, computed with `at = now()` in UTC. Another tenant's id → 404.
  - 7. `api.py`: `EligibilityApi.get_certificate(conn, certificate_id, *, at)` and
    `EligibilityApi.list_certificates(conn, *, owner_kind, owner_id, at)` for ELIGIBILITY-02/04 (read models with the
    computed fields). Other modules never read these tables; they call ELIGIBILITY-02's `check`.
  - 8. Terms in `config/terms/en-AU/eligibility.json`, listed in the manifest `term_keys`: the renamable noun
    (`eligibility.certificate.singular` "Certificate", `.plural` "Certificates"), `eligibility.expiry.green` "Valid",
    `.amber` "Expiring soon", `.red` "Expired", `.none` "No expiry", the statuses (`valid`, `expired`,
    `superseded`, `revoked`), owner kinds ("Person", "Asset") and one message key per error code above. Codes stay
    stable; only labels are terms.
- **acceptance**:
  - A certificate type stores its `enforcement` (`ignore`, `notify` or `hard_stop`, default `hard_stop`); any other
    value is a 422.
  - No column stores green/amber/red or `expired`; the API computes them from the UTC date at request time, so a
    certificate turns red at 00:00:00 UTC the day after `expires_on` with no job and no write.
  - A certificate can only belong to an existing person or asset of the caller's tenant, of the type's owner kind.
  - Supersede and revoke are the only status changes, each one transaction with its outbox event, and each event
    reaches `audit_log` through the AUDIT-02 writer.
  - Every route is permission-checked; another tenant's ids give 404 (or 422 `OWNER_NOT_FOUND` for an owner
    reference); `aip_app` cannot `DELETE` from either table.
  - The DATABASE-07 isolation suite and the schema guard pass with the two new tables.
- **tests**:
  - **unit** (`test_expiry.py`, no database):
    - `expiry_status(date(2026,10,31), 30, datetime(2026,10,31,23,59,59,tzinfo=UTC))` → `("amber", 0)`.
    - Same certificate at `2026-11-01T00:00:00Z` → `("red", -1)`.
    - At `2026-11-01T07:59:59+08:00` (Perth, = 23:59:59 UTC on 31 Oct) → `("amber", 0)`; at
      `2026-11-01T08:00:00+08:00` → `("red", -1)`. This is the ADR 0025 rule, not an AWST midnight cutoff.
    - `expires_on = 2026-11-30` at `2026-10-31T12:00Z` → `("green", 30)`; `2026-11-29` → `("amber", 29)`.
    - `amber_days = 0`, expiring today → `("green", 0)`; `expires_on = None` → `("none", None)`.
    - A naive `datetime(2026,10,31)` → `ValueError`.
    - `expires_at_utc(date(2026,10,31))` → `"2026-10-31T23:59:59Z"`.
    - `validate_reminder_offsets([7,30,60])` → `[60,30,7]`; `[30,30]` → error `duplicate offset`; `[0]` → error;
      seven values → error.
  - **integration** (`test_certificates_db.py`, pytest + testcontainers-python on real Postgres, the TESTING-01
    tenants `kaefer-demo` and `tenant-b`, the real app through httpx, permissions from a test grant provider as in
    the projects conftest; `alice` is the person owner):
    - `POST /certificate-types {"code":"CSWIP-3.1","name":"Welding Inspector","ownerKind":"person"}` → 201 with
      `amberDays: 30`, `reminderOffsets: [60,30,7]`, `requiresExpiry: true`. The same code as `cswip-3.1` → 409
      `DUPLICATE_CODE`.
    - Certificates for alice with `expiresOn` = UTC today + 10, + 30 and − 1 → `expiryStatus` `amber` (10),
      `green` (30), `red` (−1); the last has `displayStatus: "expired"` while
      `SELECT status FROM certificates WHERE id = :id` (as `aip_app`) returns `valid`.
    - SQL/Python parity: insert certificates expiring 2026-10-31 and 2026-11-29 and list them through the repository
      with each `at` from the unit table → the same `(expiry_status, days_to_expiry)` as `expiry.expiry_status`.
    - `GET /certificates?expiryStatus=amber` over the three above → exactly 1 item.
    - Type with `requiresExpiry: true` and no `expiresOn` → 422 `EXPIRY_REQUIRED`; `issuedOn 2026-10-01`,
      `expiresOn 2026-09-30` → 422 `INVALID_DATES`.
    - An `asset` type with a person owner → 422 `OWNER_KIND_MISMATCH`; a person owner id from `tenant-b` → 422
      `OWNER_NOT_FOUND`, and `certificates` row count unchanged.
    - An asset created with `AssetsApi.create_asset` owns a calibration certificate → 201;
      `GET /certificates?ownerKind=asset&ownerId=<asset>` → 1 item.
    - Supersede a valid certificate → 201 for the new one; the old one reads `status: "superseded"` with
      `supersededBy` = the new id; superseding the old one again → 409 `INVALID_STATUS_TRANSITION`;
      `domain_events` has one `certificate.superseded` row for the old id.
    - Revoke with `{"reason":"Ticket withdrawn by issuer"}` → 200, `status: "revoked"`, `statusChangedAt` set;
      revoking again → 409 `INVALID_STATUS_TRANSITION`.
    - `PATCH` with a stale `expectedSyncVersion` → 409; a body with an unknown key `{"status":"valid"}` → 422.
    - A user with only `certificate.view` POSTs a certificate → 403 and no row is written.
    - A `tenant-b` user: `GET /certificates/{kaefer id}` → 404; `GET /certificates` → 0 items.
    - As `aip_app`: `DELETE FROM certificates` → `permission denied`.
    - `DELETE /certificate-types/{id}` with a live certificate → 409 `TYPE_IN_USE`.
    - After the dispatcher runs, `expect_audited(conn, "certificate.created", record_id=<id>)` (the
      `tests/fixtures/audit.py` helper) passes.
  - **e2e**:
    - API-only task: there is no Playwright API project yet, so the HTTP journeys above run in the integration
      suite against the real app and Postgres. The browser journey (register, certificate page, cross-tenant 404,
      axe) ships with the pages in ELIGIBILITY-04.

Out of scope: company, material batch and project owners; `required_fields` per type; competency requirements and
discipline gates (later P1 rows); the document upload (ELIGIBILITY-04); reminders and availability suppression
(ELIGIBILITY-05).
