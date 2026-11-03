# PORTAL-06 — Witness notification and attendance: email the client inspector, accept, reject or reschedule in the portal (part B)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->
<!-- hand-edited: owner decision 2026-11-03, witness notification moved from INSPECTIONS-03; split into INSPECTIONS-12 (Part A) and PORTAL-06 (Part B) -->

| Field | Value |
|---|---|
| Module | [`portal`](../../docs/blueprint/modules/portal/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | INSPECTIONS-12, PORTAL-03 |
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

This task is part B. [INSPECTIONS-12](INSPECTIONS-12.md) (part A) builds the bookings, the staff API, the
references, the recipient hook and the events, and must merge first. Its design decisions D1 to D10 apply here.

**Out of scope:** the staff UI to propose a booking (INSPECTIONS-04 adds the button on the ITP steps view; this task
ships the API and an e2e fixture route only); the client's own waiver "proceed without me" (owner 2026-11-03: yes,
built by PORTAL-10 on the hook in D11); reminders before the scheduled time and "notice period ending" alerts
(owner 2026-11-03: yes, PORTAL-11); emails in the recipient's own time zone (owner 2026-11-03: later, PORTAL-12);
calendar (.ics) attachments (`EmailMessage` has no attachments yet); third-party inspectors who are not system users
(ADR 0039: QA notifies them outside the system, recorded with `notify: "outside_system"`); witnessing the point
itself and signing it in the portal (`witnessed` by a client signatory: INSPECTIONS-05 / PORTAL-04); the tzdata
recalculation job (ADR 0025 consequence; the cache is computed on write here); bulk "confirm attendance".

## Part B — portal: recipients, emails, client API, portal pages

- **files**:
  - apps/api/aip/modules/portal/witness.py (new: recipients, client service)
  - apps/api/aip/modules/portal/witness_email.py (new: composition)
  - apps/api/aip/modules/portal/events.py (subscribers), routes.py, schemas.py, manifest.toml (`subscribes`,
    `depends_on` gains `ops`, `uploads`, `terms`)
  - apps/api/aip/modules/portal/tests/{test_witness_recipients_db.py,test_witness_email.py,test_witness_routes_db.py}
  - apps/portal/src/routes/witness/{index.tsx,$bookingId.tsx}
  - apps/portal/src/witness/{WitnessList.tsx,WitnessDetail.tsx,RespondDialog.tsx,ReferencesList.tsx,format.ts}
  - apps/portal/src/witness/__tests__/{witness-detail.test.tsx,format.test.ts}
  - apps/portal/src/routes/__root.tsx (nav link), apps/portal/src/routes/signin.tsx (return path)
  - config/terms/en-AU/portal.json
  - e2e/fixtures/portal.ts (`proposeWitnessBooking`, `readMailpit`), e2e/portal/witness.spec.ts
  - packages/api-client (regenerated)
- **steps**:
  - 1. Recipients (`witness.py`): `witness_recipients(conn, project_id, asset_id) -> Recipients(active: list[user_id],
    invited_not_signed_in: int)` per D5, using `repo.unrevoked_grants`, `policies.grant_state` and the asset's
    ancestor ids from `AssetsApi`; registered with `register_witness_recipient_counter` at import.
  - 2. Email (`witness_email.py`), composed per recipient with `TermsApi.format_message` (locale en-AU, the tenant's
    and project's overrides), plain text and escaped HTML, no remote images:
    - Subject `portal.witness.email.subject.<kind>` (proposed, rescheduled, cancelled), e.g. "Witness point
      proposed: {stepTitle} on {assetTag}, {when}".
    - Body: greeting with the recipient's name; requested by `{requesterName}` of `{companyName}` (the tenant's
      display name; the requester's display name from `identity.get_display_names`); project code and name; asset
      tag and the asset path from the grant's root down (no ancestors outside the grant); ITP number and title;
      step number, title and point-type term (`itp.point_type.*`); proposed time as `Tue 10 Nov 2026, 9:00 am AWST
      (Australia/Perth)` then `01:00 UTC`; duration and location note when set; notice period in hours; for a
      reschedule, the previous time and the reason; for a cancel, the reason; the count of associated documents and
      codes; the link `${PORTAL_ORIGIN}/witness/{bookingId}`; a footer saying why they got it (their witness access
      on the project). No token, email or name in the URL; no attachments; nothing the grant does not cover
      (acceptance criteria are omitted from the email and shown in the portal).
    - Requester emails (`portal.witness.email.response.<kind>` and `.not_notified`): to the booking's requester when a
      client accepts, rejects (with the reason) or asks to reschedule (with the proposed time), and when no
      recipient was left at dispatch. The link is the staff app's ITP step page.
  - 3. Subscribers (`events.py`, manifest `subscribes`; at-least-once, ADR 0030): on `witness_booking.proposed`,
    `.rescheduled`, `.cancelled` with `notifyMode == "portal"`: resolve recipients again; none → 
    `record_witness_notify_failed(reason="no_recipient")` and the requester email; else one `ops.send_email` per
    recipient with idempotency key `witness:{bookingId}:r{revision}:{kind}:{userId}` and one
    `record_witness_notified(..., recipient_ids)`. A redelivered event queues no second email and no second
    `notified` row. On `witness_booking.responded`: the requester email, key `witness:{bookingId}:resp:{eventId}`.
    Logs carry ids only (STACK-06).
  - 4. Client API (`client_router`, `external=True`, PORTAL-02 session, CSRF and rate limits; `portal.record.witness`
    on the booking's project and asset path, else 404 — never 403, so a booking outside the grant looks missing):
    - `GET /api/v1/portal/witness?status=open|all&cursor=&limit=` (1–50): the caller's bookings from
      `list_witness_bookings` over their live `witness` grants, each re-checked with `PolicyService.can`; items
      `{id, projectCode, assetTag, stepTitle, pointType, scheduledLocal, scheduledZone, scheduledStartUtc, status,
      myLatestResponse}`.
    - `GET /api/v1/portal/witness/{bookingId}`: the page model — requester name and company, project, asset tag and
      grant-trimmed path, ITP number/title, template name and revision, step seq/title/point type/acceptance
      criteria, scheduled local/zone/UTC, duration, location, notice hours, status, revision, the caller's latest
      response, the event history (kinds, times, revision, proposed times, reasons; actors shown as the requester's
      name for staff events and the client's own company users' names for portal events; `notified` shows only
      "sent to n people"), references `{id, kind, code, title, revision, hasFile, canDownload}`, and
      `availableResponses` (empty when closed or started).
    - `POST /api/v1/portal/witness/{bookingId}/responses` `{kind, reason?, proposedLocal?, dstChoice?,
      expectedRevision, clientRequestId}` → 201 (200 on replay) with the updated page model; errors as Part A step 3;
      additionally at most 10 responses per user per booking per hour (429 `RATE_LIMITED`, the PORTAL-02 store).
    - `GET /api/v1/portal/witness/{bookingId}/references/{referenceId}/file`: needs `portal.report.download` on the
      same scope (404 otherwise, and for a reference without a file); streams `open_stored_file` with
      `Content-Disposition: attachment`, the stored filename and `Cache-Control: no-store`.
    - Each view, response and download writes one security event (`portal.witness_viewed`,
      `portal.witness_responded`, `portal.witness_file_downloaded`) with the booking id; never the reason text.
  - 5. Portal pages (`@aip/ui` only, terms only, light and dark):
    - `/witness`: "Witness and hold points" list (soonest first): step, asset tag, project, site time with zone
      abbreviation, viewer's local time as secondary text when it differs, status chip, my response; empty state;
      Load more. Header nav link "Witness points".
    - `/witness/$bookingId`: what is inspected (project, asset path, ITP, step, point type, acceptance criteria),
      who asked (name, company), when (site time, zone, local time, UTC on hover/secondary), where, notice period,
      status; actions Accept, Reject (dialog, reason required) and Propose another time (dialog: date and time in the
      site's zone, earlier/later choice when the time is ambiguous, reason required; the earliest allowed time is
      shown); "Documents and codes" list with download buttons only where `canDownload`; history list. 409
      `BOOKING_REVISED` reloads and says the time changed; 409 `BOOKING_CLOSED`/`BOOKING_STARTED` shows read-only;
      404 shows the not-found panel.
    - Sign-in return: an unauthenticated visit to `/witness/...` goes to `/signin` and back to that same-origin path
      after sign-in (path kept in `sessionStorage`; any absolute or cross-origin value is ignored).
  - 6. Terms: `portal.witness.*` (page, list, actions, dialogs, statuses, errors, email subjects and bodies) in
    `config/terms/en-AU/portal.json`; regenerate the client.
- **acceptance (Part B)**:
  - Proposing a booking emails each active client inspector whose `witness` grant covers the asset, once each, with
    the requester's name and company, the inspected item and its path, the proposed time in the site's zone with
    its abbreviation and UTC, the notice period and a plain portal link; the booking records who was notified.
  - A client with a grant on another asset subtree, a `view`-only grant, an expired or revoked grant, a suspended
    account or not yet signed in gets no email and gets 404 on the page.
  - In the portal the client accepts, rejects with a reason, or proposes another time; each response appears in the
    booking's history in the staff API and emails the requester. A reschedule by staff emails everyone again and
    the page shows the new time; a cancel emails everyone and the page is read-only.
  - The page lists the ITP, its form template revision, the step's acceptance criteria and the references; a file
    downloads only with the `download` action and through the upload pipeline.
  - A grant revoked between proposal and dispatch leaves the booking "not notified" and the requester is emailed.
- **tests (Part B)**:
  - **unit**:
    - `format.ts`: `2026-11-10T01:00:00Z`, zone `Australia/Perth`, viewer `TZ=Australia/Sydney` → primary `10 Nov
      2026, 9:00 am AWST`, secondary `12:00 pm AEDT`; viewer in Perth → no secondary.
    - `WitnessDetail` (Vitest + MSW): Reject without a reason does not send; reschedule sends `proposedLocal` and
      `expectedRevision`; 409 `BOOKING_REVISED` refetches and shows the term; download button hidden when
      `canDownload` is false; closed booking shows no actions; axe → 0 serious/critical.
    - `witness_email` (pytest, no DB): the text and HTML contain requester name, company, asset tag, step title,
      `AWST`, `UTC`, notice hours and `https://portal.example.test/witness/<uuid>`; the link has no `?`; a step title
      with `<script>` is escaped in HTML; the acceptance criteria are absent.
  - **integration** (testcontainers Postgres; Part A's fixture; portal users: P1 project-wide `["view","witness"]`
    active; P2 subtree grant on `TK-101`'s parent with `["view","witness","download"]` active; P3 `["view"]` only;
    P4 `witness` but invited, not signed in; P5 `witness` on a sibling subtree; P6 suspended; the mailer replaced by
    the recording mailer, the outbox dispatched in-test):
    - Recipients for `TK-101` → P1 and P2; `invited_not_signed_in = 1`.
    - Propose → dispatch → two `ops.send_email` jobs, one address each; booking `notified_count = 2`, one `notified`
      event with both ids; dispatch the same event again → still two jobs, one `notified` row.
    - Revoke P1 and P2 after propose, then dispatch → `notify_failed` event, one email to the requester, no client
      email.
    - P1 `GET /portal/witness` → the booking; P3, P5 → empty list and 404 on the page; a `tenant-b` portal user with
      the same booking id → 404; a staff session on the client route → 404 (PORTAL-02).
    - P2 accept → 201, status `accepted`, `witness_booking.responded` outbox row, a `portal.witness_responded`
      security event; replay with the same `clientRequestId` → 200, one event row. P1 reject → `rejected` (latest
      wins).
    - Staff reschedule → P1's `expectedRevision: 1` accept → 409 `BOOKING_REVISED`; dispatch → two `rescheduled`
      emails.
    - Download: P2 → 200 with the stored bytes, `no-store`, security event; P1 (no `download`) → 404; a reference
      with no file → 404.
    - 11 responses by P1 within the hour → the 11th is 429 `RATE_LIMITED`.
  - **e2e** (`e2e/portal/witness.spec.ts`, projects `portal` and `portal-mobile`, compose stack with Mailpit; staff
    steps through `proposeWitnessBooking`, which calls the staff API as a signed-in `kaefer-demo` supervisor):
    - Main journey: invite and onboard a client with `["view","witness","download"]` on `KF-01` (PORTAL-03
      fixtures); propose a booking on the witness step; Mailpit has exactly one message to the client whose text has
      the supervisor's name, the tenant's display name, `TK-101`, the step title, the zone abbreviation and a
      `/witness/<id>` link with no query string; open the link signed out → sign in → land on that booking; the
      page shows the step, the references and the acceptance criteria; download a reference (a file is saved);
      Accept → status chip accepted; Mailpit has one message to the supervisor.
    - Reschedule: the client proposes another time with a reason → staff API shows `reschedule_requested`; staff
      reschedules → a second client email and the page shows the new time after reload.
    - Reject needs a reason: the dialog blocks submit while empty.
    - Cross-grant: a second client granted only on another project gets no email and sees 404 for the booking URL.
    - Cross-tenant: a `tenant-b` client opening the same URL sees the not-found panel.
    - axe (serious/critical) on `/witness` and `/witness/$bookingId`, on both projects; the detail page fits a phone
      without horizontal scroll.

## Owner answers (2026-11-03)

1. **Split.** Part A is its own row, INSPECTIONS-12 (the task linter allows one module and at most size M per task).
2. **Client waiver: yes.** The client may waive ("proceed without me"). It is a client sign-off (ADR 0010 critical
   action); INSPECTIONS-12 D11 adds the hook and PORTAL-10 builds the portal side.
3. **Waiver rule: both grounds.** Staff may waive an open booking when the client rejected it, or when the booked
   time has passed and the client did not attend (INSPECTIONS-12 D4).
4. **Notice period: a project setting.** `witness_notice_hours` from PROJECTS-04 (24 h until it ships); a step's
   `notice_hours` no longer sets it (INSPECTIONS-12 D3).
5. **Time zone: site time for R1.** Later the email and pages must show the recipient's own time zone (PORTAL-12).
6. **Reminders: yes.** Reminders before the booked time and "notice period ending" alerts are PORTAL-11.
7. **Hold points: yes.** Hold points are bookable and notified the same way (INSPECTIONS-12 D2).

## Dependencies

INSPECTIONS-12 (part A) and PORTAL-03 (portal app, `e2e/fixtures/portal.ts`, Mailpit reader). PROJECTS-04 is a
soft dependency (24 h fallback). PORTAL-04 is no longer needed (responses are not sign-offs, D8). No notifications
module exists; email uses `ops.send_email` (STACK-06), the same job identity's invites use.
