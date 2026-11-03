# INSPECTIONS-12 — Witness bookings on ITP steps: propose, reschedule, cancel, references, recipient hook and events (witness notification, part A)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->
<!-- hand-edited: owner decision 2026-11-03, witness notification moved from INSPECTIONS-03; split into INSPECTIONS-12 (Part A) and PORTAL-06 (Part B) -->

| Field | Value |
|---|---|
| Module | [`inspections`](../../docs/blueprint/modules/inspections/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | INSPECTIONS-03, PORTAL-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/portal/README.md`](../../docs/blueprint/modules/portal/README.md); only if a step needs it,
   the "Witness and hold points (portal)" register in
   [`features-access.md`](../../docs/blueprint/modules/portal/features-access.md) and `inspection_bookings` in
   [`inspections/data-model.md`](../../docs/blueprint/modules/inspections/data-model.md) (shape reference, not copied)
3. ADRs: [0039](../../docs/adr/0039-owner-answers-item-types-witness-root-cause.md) (#43 witness notification, with the
   owner's 2026-11-03 line, and Consequences), [0036](../../docs/adr/0036-r1-module-decisions.md) ("Owner answers"
   portal lines: notice period and waiver rule are project settings), [0025](../../docs/adr/0025-time-and-timezones.md)
   (§4 wall-clock model for future scheduled events), [0010](../../docs/adr/0010-signoff-assurance.md) (what is a
   critical action), [0030](../../docs/adr/0030-outbox-dispatch-semantics.md) (at-least-once subscribers),
   [0034](../../docs/adr/0034-invites-and-step-up-implementation.md) (email via a job), [0005](../../docs/adr/0005-identity-architecture.md)
4. Code to build on: `apps/api/aip/modules/inspections/{itp.py,itp_rules.py,schemas.py,tables.py,api.py,events.py}`
   (INSPECTIONS-03); `apps/api/aip/modules/portal/{policies.py,grant_provider.py,routes.py,rate_limit.py,api.py,events.py}`
   (PORTAL-01/02); `apps/api/aip/modules/ops/jobs.py` (`send_email`, STACK-06); `apps/api/aip/modules/terms/api.py`
   (`format_message`); `apps/api/aip/modules/uploads/api.py` (`get_stored_file`, `open_stored_file`, UPLOADS-08);
   `apps/portal/` and `e2e/fixtures/portal.ts` (PORTAL-03)

## Spec

When staff propose a date and time for a witness point (or a hold point the client attends), the system emails every
client inspector who holds a portal grant covering that point: who requested it (person and company), what is being
inspected and where, the proposed time in the site's zone, the notice period, and a plain link to the portal page.
There the client accepts, rejects (with a reason) or proposes another time, and sees the point's associated documents
and codes. The proposal, every notification and every response are recorded on the witness point, append-only and
audited (ADR 0039 #43, owner 2026-11-03; tag: extend — INSPECTIONS-03 shipped the points without the notification).

This task is part A of the witness notification. [PORTAL-06](PORTAL-06.md) (part B) sends the emails and builds the
client's portal pages on top of it, and starts only after this merges. The design decisions D1 to D10 below are
shared by both tasks.

**Out of scope:** the staff UI to propose a booking (INSPECTIONS-04 adds the button on the ITP steps view; this task
ships the API and an e2e fixture route only); the client's own waiver "proceed without me" (open question 2);
reminders before the scheduled time and "notice period ending" alerts (PORTAL-08-style follow-up, open question 6);
calendar (.ics) attachments (`EmailMessage` has no attachments yet); third-party inspectors who are not system users
(ADR 0039: QA notifies them outside the system, recorded with `notify: "outside_system"`); witnessing the point
itself and signing it in the portal (`witnessed` by a client signatory: INSPECTIONS-05 / PORTAL-04); the tzdata
recalculation job (ADR 0025 consequence; the cache is computed on write here); bulk "confirm attendance".

### Design decisions (read before the steps)

- **D1 — Trigger.** A new staff action *propose a witness booking* on a step, not the existing `ready` action. `ready`
  carries no date; ADR 0039 says notify "when a witness point is booked". Proposing on a `pending` step also performs
  `ready` (sets `ready_at`) in the same transaction, so the notice given and the booking line up. Re-notification on
  every reschedule (new `revision`) and on cancel. A released or waived step closes its open booking (`done`, no email).
- **D2 — Point types.** `witness` and `hold` steps may be booked (`review` and `surveillance`: 422 `NOT_A_WITNESS_POINT`).
  A hold point booking invites the client to attend the release; the release itself stays PORTAL-04's.
- **D3 — Notice period.** Effective notice = `max(project witness_notice_hours, step.notice_hours or 0)`: the project
  setting is the floor, a step may only lengthen it (ADR 0036 makes it a project setting; INSPECTIONS-03's per-step
  `notice_hours` stays as an override that can only tighten). The value is snapshotted on the booking at each
  revision. `witness_notice_hours` is read through `ProjectsApi.get_setting` when PROJECTS-04 ships it; until then
  every project uses `DEFAULT_WITNESS_NOTICE_HOURS = 24` (the same fallback pattern as PORTAL-01's
  `portal_access_days`), so PROJECTS-04 is not a hard dependency. A proposal or reschedule whose start is earlier
  than `now + notice` is 422 `NOTICE_TOO_SHORT`.
- **D4 — Waiver clock.** INSPECTIONS-03 lets staff waive a witness point once `ready_at + notice_hours` has passed.
  With a booking that is too early (the client may have accepted a time three days out). New rule in `itp_rules`:
  `waived` also needs, when the step has an open booking, either the booking `rejected` by the client or
  `now >= scheduled_start_utc` (the witness did not attend); otherwise 409 `BOOKING_OPEN`. Without a booking the old
  rule holds unchanged. This is how the project's `witness_waiver_rule` is applied in R1 (open question 3).
- **D5 — Recipients.** Every portal user who is `active` (signed in at least once, not suspended, identity user
  active) and holds a live grant with the `witness` action whose scope covers the step's asset (project-wide, or a
  subtree grant whose root is the asset or one of its ancestors). Invited users who have not signed in are not
  emailed (they could not act; their count is reported). One email per recipient, `to` one address only, so no
  client sees another's address.
- **D6 — Fail visibly, never silently.** With `notify: "portal"` and no recipient, the proposal is refused (422
  `NO_WITNESS_RECIPIENT` with `invitedNotSignedIn: n`) and nothing is written; the staff member either invites or
  renews a client (PORTAL-07) or proposes with `notify: "outside_system"` and a note saying who was told and how
  (ADR 0039: third-party inspectors). If recipients disappear between commit and dispatch (grant revoked), the
  subscriber records `notify_failed` on the booking and emails the requester; the booking shows "not notified".
- **D7 — Module boundary.** `portal` already depends on `inspections` (PORTAL-03); `inspections` must not import
  `portal`. Inspections exposes `register_witness_recipient_counter(fn)` in `api.py` (the `register_action_permissions`
  pattern); portal registers its counter at import. With no counter registered (portal disabled), `notify: "portal"`
  is 422 `NO_WITNESS_RECIPIENT`. Emails are sent by portal subscribers on inspections' events, never by inspections.
- **D8 — Responses are not sign-offs.** Accept, reject and reschedule attest nothing about the work, so they are not
  ADR 0010 critical actions and ask for no step-up; each response row records the session's assurance method and
  level (`derive_assurance`) as `itp.reject` does. The portal session already carries the second factor (ADR 0036).
- **D9 — Time.** ADR 0025 §4: `scheduled_local` (`timestamp without time zone`) + `scheduled_zone` (IANA; the site's
  zone, else the project's, else required in the body) + `scheduled_start_utc` (cache). A skipped or repeated local
  time needs `dstChoice: "earlier" | "later"` (422 `AMBIGUOUS_LOCAL_TIME` / `NONEXISTENT_LOCAL_TIME` otherwise). The
  email shows the site-zone time with its abbreviation and the IANA name, then UTC; the recipient has no stored zone
  preference yet (open question 5). The portal page shows site time first and the viewer's local time second.
- **D10 — Documents and codes.** Nothing links documents to steps today, so Part A adds `itp_references` (ITP-wide or
  per step): a kind (`drawing`, `specification`, `standard`, `procedure`, `other`), a code, a title, a revision and
  an optional clean stored file. The portal page also shows the ITP's number and title, its form template name and
  revision, the step's acceptance criteria and the asset tag and path. A file downloads only through UPLOADS-08
  (`open_stored_file`) and only with the grant's `download` action; without it the client sees the code and title.

## Part A — inspections: bookings, references, staff API, events

- **files**:
  - apps/api/migrations/versions/<timestamp>_inspections_witness_bookings.py
  - apps/api/aip/modules/inspections/tables.py
  - apps/api/aip/modules/inspections/witness.py (new: booking service)
  - apps/api/aip/modules/inspections/witness_time.py (new: pure wall-clock helpers)
  - apps/api/aip/modules/inspections/references.py (new)
  - apps/api/aip/modules/inspections/itp_rules.py, itp.py (waiver clock, close booking on release)
  - apps/api/aip/modules/inspections/repository.py, schemas.py, routes.py, api.py, events.py, manifest.toml
  - apps/api/aip/modules/inspections/tests/{test_witness_rules.py,test_witness_time.py,test_witness_db.py,test_references_db.py}
  - packages/contracts/events/witness_booking.{proposed,rescheduled,cancelled,responded,closed}.v1.json
  - config/terms/en-AU/inspections.json
  - packages/api-client (regenerated)
- **steps**:
  - 1. Migration (one revision, forward-only, ADR 0002):
    - `witness_bookings` from `render_template("tenant_table", sync=True, ...)`: `inspection_id`, `itp_step_id`,
      `asset_id`, `project_id uuid NULL` (copied from the ITP), `revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1)`,
      `status text NOT NULL CHECK (status IN ('proposed','accepted','rejected','reschedule_requested','cancelled','done'))`,
      `scheduled_local timestamp NOT NULL`, `scheduled_zone text NOT NULL`, `scheduled_start_utc timestamptz NOT NULL`,
      `duration_minutes integer NULL CHECK (duration_minutes BETWEEN 15 AND 720)`, `location_note text NULL`
      (≤ 500), `notice_hours integer NOT NULL CHECK (notice_hours BETWEEN 0 AND 720)`, `notify_mode text NOT NULL CHECK
      (notify_mode IN ('portal','outside_system'))`, `outside_note text NULL` (required by CHECK when
      `outside_system`, ≤ 500), `requested_by uuid NOT NULL`, `notified_at timestamptz NULL`,
      `notified_count integer NOT NULL DEFAULT 0`. FKs `(itp_step_id, tenant_id)` → `itp_steps`,
      `(inspection_id, tenant_id)` → `inspections`; unique partial index `(tenant_id, itp_step_id) WHERE deleted_at IS
      NULL AND status IN ('proposed','accepted','rejected','reschedule_requested')` (one open booking per step);
      indexes `(tenant_id, project_id, scheduled_start_utc)`, `(tenant_id, asset_id)`.
    - `witness_booking_events`, append-only like `inspection_signoffs` (no `updated_at`/`deleted_at`; `GRANT SELECT,
      INSERT` to `aip_app`; `REVOKE UPDATE, DELETE, TRUNCATE`): `booking_id`, `revision`, `seq` (`UNIQUE (booking_id,
      seq)`), `kind CHECK (kind IN ('proposed','rescheduled','cancelled','notified','notify_failed','accepted',
      'rejected','reschedule_requested','closed'))`, `actor_user_id uuid NULL` (NULL for system), `actor_class text
      CHECK (actor_class IN ('staff','portal','system'))`, `reason text NULL` (≤ 2000), `proposed_local timestamp NULL`,
      `proposed_zone text NULL`, `proposed_start_utc timestamptz NULL`, `recipient_user_ids uuid[] NULL`,
      `assurance_method text NULL`, `assurance_level smallint NULL`, `client_request_id uuid NULL` (unique per
      `(booking_id, client_request_id)` where set), `created_at timestamptz NOT NULL DEFAULT now()`.
    - `itp_references` (`tenant_table`, soft delete): `inspection_id`, `itp_step_id uuid NULL` (NULL = whole ITP),
      `kind CHECK (kind IN ('drawing','specification','standard','procedure','other'))`, `code text NOT NULL`
      (1–100), `title text NULL` (≤ 200), `revision text NULL` (≤ 40), `stored_file_id uuid NULL`, `created_by uuid
      NOT NULL`; index `(tenant_id, inspection_id)`.
    - All three FORCE ROW LEVEL SECURITY with the fail-closed tenant policy; `aip-db check-schema` matches `tables.py`.
  - 2. `witness_time.py` (pure): `to_utc(local, zone, dst_choice) -> datetime` using `zoneinfo` (`fold=0` earlier,
    `fold=1` later), raising `AmbiguousLocalTime` / `NonexistentLocalTime` when no choice is given; `zone_for(site_tz,
    project_tz, body_zone)` (first non-null; an unknown IANA name → 422 `INVALID_TIME_ZONE`); `effective_notice_hours(
    project_hours, step_hours) = max(project_hours, step_hours or 0)`.
  - 3. `witness.py` `WitnessService` (each call in the caller's `with_tenant`; locks ITP, then step, then booking):
    - `propose(conn, actor, step_id, body)` (`itp.manage` on the ITP's project): checks in order 404 (step not
      visible) → 403 → 422 `NOT_A_WITNESS_POINT` → 409 `INVALID_STEP_ACTION` (step not `pending`/`ready`) → 409
      `BOOKING_EXISTS` → 422 time errors → 422 `NOTICE_TOO_SHORT` (`{noticeHours, earliestUtc}`) → for
      `notify: "portal"`, the registered counter (D7) returns `(active, invited_not_signed_in)`; `active == 0` → 422
      `NO_WITNESS_RECIPIENT` `{invitedNotSignedIn}`. Then: `ready` on a pending step, the booking (revision 1,
      `proposed`), event `proposed`, outbox `witness_booking.proposed` v1. Idempotent on `clientRequestId` (same id →
      the same booking, 200 instead of 201).
    - `reschedule(conn, actor, booking_id, body)` (`itp.manage`): `reason` required (422 `COMMENT_REQUIRED`),
      `expectedRevision` must match (409 `BOOKING_REVISED` with the current booking); open bookings only (409
      `BOOKING_CLOSED`); notice check again from now; revision + 1, status `proposed` (earlier responses no longer
      count), event `rescheduled`, outbox `witness_booking.rescheduled` v1.
    - `cancel(conn, actor, booking_id, reason)` (`itp.manage`): open bookings only; status `cancelled`, event,
      outbox `witness_booking.cancelled` v1. The step stays `ready`; a new booking may then be proposed.
    - `get_for_step(conn, actor, step_id)` (`inspection.view`): the open (else latest) booking with its full event
      history, and the requester's display name (`identity.get_display_names`).
    - Published for portal (`api.py`, no policy check: the portal has decided access first, as PORTAL-03's inbox
      does): `register_witness_recipient_counter(fn)`; `witness_booking_view(conn, booking_id)` (booking, step,
      ITP number/title, template name and revision, asset id, project id, requester id, references, events);
      `list_witness_bookings(conn, scopes, status, after, limit)` (open bookings in `[(project_id, asset_id | None)]`
      scopes, soonest `scheduled_start_utc` first, keyset cursor); `record_witness_notified(conn, booking_id,
      revision, kind, recipient_ids)` (idempotent per `(booking_id, revision, kind)`; sets `notified_at`,
      `notified_count`); `record_witness_notify_failed(conn, booking_id, revision, reason)`;
      `respond_witness(conn, booking_id, *, responder_user_id, kind, reason, proposed_local, expected_revision,
      client_request_id, assurance)` which validates (below), appends the event, sets the booking status and emits
      `witness_booking.responded` v1.
    - Response rules (`respond_witness`): kinds `accept` → `accepted`, `reject` → `rejected` (reason 1–1000
      required, 422 `COMMENT_REQUIRED`), `reschedule` → `reschedule_requested` (reason required and `proposedLocal`
      in the booking's zone, at or after `now + notice`, else 422 `NOTICE_TOO_SHORT`; DST rules as D9). Refused when
      the booking is `cancelled`/`done` (409 `BOOKING_CLOSED`), when `now >= scheduled_start_utc` (409
      `BOOKING_STARTED`), or on a stale `expectedRevision` (409 `BOOKING_REVISED`). A replayed `clientRequestId`
      returns the first result and writes nothing. A later response from the same or another recipient on the same
      revision is appended and becomes the booking status (latest wins; history keeps all).
  - 4. Rules: `itp_rules.apply_decision` gains an optional `booking` fact (`status`, `scheduled_start_utc`); for
    `waived` with an open booking, refuse with 409 `BOOKING_OPEN` unless `status == "rejected"` or
    `now >= scheduled_start_utc` (D4). `ItpService.sign` passes the step's open booking. A step that becomes
    `released` or `waived` closes its open booking in the same transaction (status `done`, event `closed`, outbox
    `witness_booking.closed` v1; no email).
  - 5. References (`references.py`, routes under `/api/v1/inspections/{inspectionId}/references`): `GET`
    (`inspection.view`), `POST` (`itp.manage`; `itpStepId` must belong to the inspection, 422 `STEP_NOT_IN_ITP`;
    `storedFileId` must be a clean stored file of the same project via `get_stored_file`, else 422
    `FILE_NOT_FOUND`), `DELETE /{referenceId}` (soft delete, `itp.manage`). Allowed while the step is not released
    or waived (409 `ITP_LOCKED` otherwise).
  - 6. Staff routes: `POST /api/v1/inspections/itp-steps/{stepId}/witness-booking` (201), `GET` the same path,
    `PATCH /api/v1/inspections/witness-bookings/{bookingId}` (reschedule), `POST
    /api/v1/inspections/witness-bookings/{bookingId}/cancel`. Error codes get message keys in `MESSAGE_KEYS` and
    terms in `config/terms/en-AU/inspections.json` (`itp.witness.*`, `itp.reference.kind.*`,
    `itp.witness.status.*`). Regenerate the client.
  - 7. Events (`events.py`, manifest `[[events]]`, frozen JSON schemas in `packages/contracts/events`): payloads
    carry ids and codes only, never names, emails or reasons: `witness_booking.proposed|rescheduled|cancelled|closed`
    v1 `{bookingId, stepId, inspectionId, projectId, assetId, pointType, revision, scheduledStartUtc, requestedBy,
    notifyMode}`; `witness_booking.responded` v1 `{bookingId, stepId, revision, responseKind, responderUserId}`.
    Aggregate `witness_booking`. These are the audit trail of the booking (with the event rows in step 1).
- **acceptance (Part A)**:
  - Proposing a time for a witness step at least the notice period away returns the booking with the local time, its
    zone and the UTC instant; a pending step becomes `ready`; one `proposed` event row and one outbox event exist.
  - With no active client grant covering the asset, the proposal is refused with `NO_WITNESS_RECIPIENT` and the
    count of invited-not-signed-in clients, and nothing is written; `notify: "outside_system"` with a note succeeds,
    and its event carries `notifyMode: "outside_system"` so no portal email follows.
  - Notice = the larger of the project setting (24 h until PROJECTS-04) and the step's `notice_hours`.
  - A rescheduled booking has a new revision and its earlier responses no longer set its status; a cancelled one
    accepts no response.
  - A witness step with an accepted booking cannot be waived before the booked time; after it, or once the client
    rejected, it can (still with the INSPECTIONS-03 comment and notice rules).
  - Booking events and references cannot be updated or deleted by `aip_app`; another tenant's step or booking is 404.
- **tests (Part A)**:
  - **unit**:
    - `effective_notice_hours(24, None) = 24`, `(24, 48) = 48`, `(48, 24) = 48`, `(0, None) = 0`.
    - `to_utc(2026-11-10 09:00, "Australia/Perth") = 2026-11-10T01:00:00Z`; `2026-04-05 02:30` in
      `Australia/Sydney` without a choice → `AmbiguousLocalTime`, with `earlier` → `15:30Z` on the 4th, `later` →
      `16:30Z`; `2026-10-04 02:30` in `Australia/Sydney` → `NonexistentLocalTime`; `"AWST"` as a zone → invalid.
    - Waiver rule table: no booking, notice elapsed → `waived`; open `accepted` booking, notice elapsed, before
      start → `BOOKING_OPEN`; same after start → `waived`; `rejected` booking before start → `waived`.
  - **integration** (`test_witness_db.py`, testcontainers Postgres, `kaefer-demo` and `tenant-b`; the INSPECTIONS-03
    fixture ITP `ITP-101` on `TK-101` in `KF-01` (zone `Australia/Perth`) with 1 hold, 2 witness `noticeHours: 48`,
    3 review; a stub recipient counter registered by the test returning `(1, 0)` unless stated):
    - Propose step 2 for now + 72 h → 201, step 2 `ready`, booking revision 1 `proposed`, `notice_hours = 48`, one
      `proposed` event, one `witness_booking.proposed` v1 outbox row whose payload has no name or email.
    - Propose step 2 for now + 30 h → 422 `NOTICE_TOO_SHORT` with `noticeHours: 48`; step 3 → 422
      `NOT_A_WITNESS_POINT`; a second proposal on step 2 → 409 `BOOKING_EXISTS`; the same `clientRequestId` again →
      200 with the first booking.
    - Counter returns `(0, 2)` → 422 `NO_WITNESS_RECIPIENT` `invitedNotSignedIn: 2`; no booking, no event, no outbox
      row, step 2 still `pending`. `notify: "outside_system"` without a note → 422; with one → 201.
    - Reschedule with `expectedRevision: 1` → revision 2; again with `1` → 409 `BOOKING_REVISED`; without reason →
      422 `COMMENT_REQUIRED`. Cancel → `cancelled`; `respond_witness` afterwards → 409 `BOOKING_CLOSED`.
    - `respond_witness` accept → `accepted`; reject without reason → 422; reschedule at now + 10 h → 422
      `NOTICE_TOO_SHORT`; a replayed `clientRequestId` → same event id, one row; after `scheduled_start_utc` (fixture
      clock) → 409 `BOOKING_STARTED`.
    - Waiver: accepted booking, `ready_at` 50 h back, before start → `sign(waived)` 409 `BOOKING_OPEN`; booking
      rejected → 200 and the booking is `done` with a `closed` event.
    - Releasing the hold step 1 leaves step 2's booking open; `witnessed` on step 2 closes it.
    - As `aip_app`, `UPDATE`/`DELETE` on `witness_booking_events` → permission denied.
    - A `tenant-b` user on a `kaefer-demo` step or booking id → 404; viewer without `itp.manage` → 403 on propose.
    - References: a step reference with a clean stored file of `KF-01` → 201; a file of another project → 422
      `FILE_NOT_FOUND`; a step of another ITP → 422 `STEP_NOT_IN_ITP`; `witness_booking_view` lists ITP-wide and
      step references and omits the soft-deleted one.

## Open questions for the owner

See [PORTAL-06](PORTAL-06.md#open-questions-for-the-owner); D2, D3 and D4 here depend on questions 3, 4 and 7.

## Dependencies

INSPECTIONS-03 and PORTAL-01 (both done). PROJECTS-04 is a soft dependency: `witness_notice_hours` uses the 24 h
fallback until `ProjectsApi.get_setting` exists.
