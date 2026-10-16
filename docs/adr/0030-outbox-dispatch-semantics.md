# ADR 0030: Outbox dispatch semantics and the dead-letter queue

- **Status:** accepted
- **Date:** 2026-10-15
- **Affects:** arch (ARCH-07), every module that subscribes to events; AUDIT-02, ACCESS-04

## Context

ADR 0003 chose a Postgres outbox (`domain_events`) drained by a Procrastinate job on the `outbox`
queue with `SKIP LOCKED`. ARCH-07 builds that dispatcher. Several behaviours were not pinned down:
what happens when one of several subscribers of an event fails, how many times an event may be
delivered, how operators see and act on dead letters across tenants, and how the PR #55 review's
low findings (consumer ownership, write-once publish columns, bounded `last_error`) are closed.

## Decision

1. **One transaction per event.** All subscribers of an event run in one `aip_app` transaction
   bound to the event's tenant (`use_context` + `with_tenant`). Either every subscriber's effect
   commits and the event is published, or none does and the event is retried. Subscribers run
   with the event's `actor_id` and `project_id` and request id `outbox-<event id>`.
2. **Claim with a lease, at least once.** The claim (`aip_jobs`, `FOR UPDATE SKIP LOCKED`)
   counts the try (`attempts + 1`) and leases the event (`next_attempt_at = now() + lease`,
   default 300 s) in a short transaction; each outcome is then recorded in its own transaction.
   No transaction stays open while subscribers run, a cancelled run loses at most the events
   in flight, and an event whose delivery hangs or dies comes back when the lease runs out with
   the try already counted, so it still reaches the dead-letter queue (dead-lettered at claim
   once `max_attempts` tries ended without an outcome). A crash, or a lease that runs out
   mid-delivery, redelivers; handlers must be idempotent on `event.id`. `attempts` counts
   tries, including a successful one.
3. **Backoff and dead letters.** A failure sets `last_error` and
   `next_attempt_at = now() + base * 2^(attempts-1)`
   (base 2 s, capped at 1 h). At `max_attempts` (default 10) the event is dead-lettered and is never
   claimed again on its own. Settings come from `OUTBOX_*` environment variables.
4. **Ownership.** A subscriber belongs to the module whose `events.py` registers it, must be listed
   in that module's manifest `subscribes` (boot fails otherwise, in the API and the worker), and
   runs only when that module is loaded.
5. **Write-once.** A trigger makes `published_at` and the discard columns write-once for every role,
   SECURITY DEFINER functions included.
6. **Operator dead-letter queue.** Three `SECURITY DEFINER` functions owned by `aip_owner`, `EXECUTE`
   to `aip_app` only, as in ADR 0029: `outbox_dead_letters` (metadata only, never a payload),
   `outbox_retry` (back to attempt 1) and `outbox_discard` (reason required, final). The routes
   need `platform.events.manage` and emit `platform.outbox.retried` / `platform.outbox.discarded`
   into the operator's tenant outbox, like `platform.event.deprecated`.
7. **Threshold alert.** At most once a minute (`alert_interval_s`), a tenant with more than `dead_letter_alert_threshold`
   (default 10) live dead letters gets one `platform.outbox.dead_letter_threshold_exceeded` event in
   its own outbox per hour (serialised with a per-tenant advisory lock), plus a structured warning.

## Consequences

- Subscribers stay simple (one connection, one transaction) but one slow or failing subscriber
  delays the others for that event; split heavy work into a job the subscriber defers.
- `last_error` holds only `<subscriber>: <ExceptionType> (<driver error>) [SQLSTATE]`, never the
  exception message, because messages can carry tenant data (bound SQL parameters, validation
  inputs) and operators read dead letters across tenants. The full text goes to the
  structured log. The column is capped at 4000 characters by constraint.
- **Accepted risk:** `aip_app` can execute the three dead-letter functions directly, so the
  `platform.events.manage` route check is their only authorisation, and `outbox_discard` trusts
  the `actor` it is given. This matches ADR 0029 (authorisation lives in the policy service,
  RLS is defence in depth). The functions never return a payload, retry is reversible and
  discard is audited. Moving the check into the database is a follow-up if a module ever
  needs raw SQL against these functions.
- The discard and retry audit events go to the operator's tenant only; the affected tenant
  sees the event's state, not an event of its own.
- Payload inspection in the dead-letter drawer and replay ranges (module README) are not built yet;
  they need a later task with its own access rules.

## Amendment (2026-10-16, OPS-03): jobs emit events

`aip_jobs` gets `INSERT` on `domain_events` (revision `202610161600_jobs_emit_events`). A job
handler runs on the `aip_jobs` engine, and its writes, its final status and the event announcing
it (`job.completed`, `job.failed`, or a module event) must commit together, exactly as a request's
do. The tenant policy and the write-once trigger apply to `aip_jobs` as to `aip_app`; it still
cannot delete or rewrite an event.
