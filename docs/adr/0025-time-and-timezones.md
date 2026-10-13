# ADR 0025: Time and time zones: UTC instants, wall-clock future events, calendar-day expiry

- **Status:** accepted (owner, 2026-10-13: "UTC everywhere internally, localise at presentation"); point 5 picks the
  reference zone for calendar-day expiry and needs the owner's confirmation
- **Date:** 2026-10-13
- **Affects:** every module that stores or shows dates and times; identity (`tenant_membership.valid_from`/`valid_to`),
  projects and sites (`timezone`), inspections and hold points (scheduled work), audit, web and field UIs

## Context

A local test run found that membership validity is checked against Postgres `current_date`, which is the UTC date. In
Perth (UTC+8, no daylight saving) a membership whose `valid_to` is "today" stays valid until 08:00 the next morning
local time. The owner answered with a time-handling standard: one clock inside the system (UTC), local time only
at the edges, and two exceptions: future scheduled events, and calendar-day deadlines.

## Decision

1. **Instants are UTC.** Every moment in time is stored as `timestamptz` and compared in UTC. Servers, containers,
   workers and database sessions run with `TZ=UTC`. APIs send and accept RFC 3339 strings with an explicit offset; the
   API emits `Z`. This covers created/updated times, audit logs, outbox events (ARCH-05), sign-offs, sessions and jobs.
2. **Past events are shown in the viewer's zone.** The client formats the UTC instant with `Intl.DateTimeFormat` in the
   user's preferred IANA zone (a profile setting), else the device zone. Recent events may show relative time ("3 hours
   ago"). Where a user's device zone differs from their saved preference, the UI shows the zone abbreviation.
3. **Where an action happened is metadata, never a changed timestamp.** When audit or compliance needs it, store the
   client's IANA zone and offset next to the UTC instant (for example on sign-off and audit records).
4. **Future scheduled events use the wall-clock model.** An inspection, hold point, witness point or site visit is
   stored as local date and time (`timestamp without time zone`) plus the IANA zone of the site or project
   (`sites.timezone`, `projects.timezone`), plus a cached UTC instant for indexing and dispatch. The cache is
   recalculated when the event changes and when tzdata is updated. Location-bound events are shown in the site's zone,
   with the viewer's local time as secondary text. Ambiguous or skipped local times at daylight-saving changes are
   resolved with an explicit earlier/later choice, and the UI asks the user. Zones are always IANA identifiers, never
   raw offsets or abbreviations.
5. **Calendar-day expiry has one reference zone: UTC.** Rules that say "valid until the end of a date", such as
   `tenant_membership.valid_to`, are inclusive through 23:59:59 UTC on that date and are checked against the UTC date,
   as the code does today. The UI must say so: "Expires 31 Oct 2026, 11:59 PM UTC (1 Nov, 7:59 AM your time)". Travel
   cannot move the cutoff. *Alternative the owner may choose instead:* anchor the cutoff to the tenant's (or
   organisation's) IANA zone at provisioning, converted to a UTC instant. That makes "today" end at local midnight in
   Perth but needs a tenant time-zone setting and a change to the membership check.
6. **Point-in-time expiry is a UTC instant.** Sessions, invite links, trials and API client credentials expire at an
   exact `timestamptz`, never at "end of day".

## Consequences

- No code change is needed for memberships unless the owner picks the alternative in point 5. TESTING-11 (PR #53)
  already makes the test use the database date.
- Tasks that add scheduled work (inspections, hold and witness points) must use the three-column wall-clock pattern in
  point 4; tasks that show expiry dates must show the UTC cutoff and the local equivalent.
- The web and field UIs need a "preferred time zone" profile setting (IANA list) and a shared date-formatting helper in
  `packages/ui`.
- A background job to recalculate cached UTC instants after tzdata updates is needed once future events exist.
