# ADR 0039: Worker heartbeat, outbox smoke checks and the dev-only approvals demo host

- **Status:** accepted
- **Date:** 2026-10-28
- **Affects:** ops (worker), platform events, approvals, identity seeds, infra; TESTING-13 (with APPROVALS-07 merged)

## Context

Review 11 M10: the worker's healthcheck was `python -c "import aip"`, and nothing in CI or the demo
checked that `project.created` was published or audited. A crash-looping worker, a wrong
`DATABASE_AUDIT_WRITER_URL` or a dispatcher that never drained all shipped green. ADR 0035 §9 carried
APPROVALS-02's two Playwright API journeys forward because no record type existed whose workflow,
permissions and fixture users a deployed stack could seed.

## Decision

1. **The worker writes a heartbeat file; the healthcheck reads it.** Every
   `WORKER_HEARTBEAT_INTERVAL_S` (10 s) the running worker runs `select 1` as `aip_jobs` and, when it
   works the `outbox` queue, as `aip_audit_writer`. A good probe rewrites `WORKER_HEARTBEAT_FILE`
   (`/tmp/aip-worker-heartbeat`, a tmpfs); a failed one deletes it. `python -m aip.worker_health
   --max-age 45` (standard library only) is the compose and Coolify healthcheck. The worker does not
   exit on a failed probe: it is reported unhealthy, and the orchestrator decides.
2. **The outbox-lag check reads `domain_events` as `aip_jobs`** (`python -m aip.platform.events.lag`),
   through the dispatcher's existing `dispatcher_select` policy, so it needs no new grant, function or
   unauthenticated endpoint. It fails on an event unpublished and undiscarded for longer than
   `--max-age`, or on a dead-lettered event an operator has not discarded. CI runs it in the compose
   `worker` container. `tools/smoke.py` stays HTTP-only and unchanged: exposing cross-tenant outbox
   state over HTTP would need a SECURITY DEFINER aggregate and a new public route, which this task
   does not justify. On the Coolify demo the real worker healthcheck covers a dead worker.
3. **"Published and audited" is checked in the stack, not through an API.** No audit read API exists
   yet (AUDIT-04). `infra/docker/smoke_outbox_audit.py` runs in the `api` container as `aip_app`, bound
   to `kaefer-demo`, and waits up to 60 s for every `project.created`,
   `workflow.definition_published` and `workflow.transitioned` event there to have `published_at`
   and an `audit_log` row (security-stream events go to `security_audit_events` and are not checked).
4. **The approvals demo host is dev-only code inside the approvals module** (`approvals/demo.py`).
   Record type `approvals_demo`, definition key `demo`, published by the `approvals-seed` one-shot as
   `aip_app`. It uses real catalogue codes (`approvals.start` to submit, `approvals.design` to approve
   or reject) that the fixture admin holds through `tenant_admin`, so no test-only code enters the
   catalogue. The resolver, the guard facts provider and the fixture switch
   (`PUT /api/v1/approvals/demo-records/{id}/facts`, `approvals.design`, hidden from OpenAPI) answer
   only when `AIP_ENV` is `development`, `test` or `demo`; elsewhere the record is invisible (404)
   and the guard fails closed. The facts live in the API process's memory: the compose API is one
   process, and a lost fact only makes the guard fail closed again.
5. **The demo's critical `approve` uses its own sign-off action, `approvals.demo_approve`, at min
   aal 1** (seeded by the identity dev seed in `kaefer-demo`). The mock IdP has no second factor, so
   an aal 2 policy would turn every approval into a pending countersign. Freshness (10 minutes) still
   applies, so the journey signs in again before approving. The aal 2 step-up journey stays with
   IDENTITY-08.

## Consequences

- A worker that cannot reach either database is unhealthy within about 45 s, in compose and on the
  demo, and `up --wait` fails in CI.
- The `e2e-skeleton` lane fails when the outbox does not drain, when an event is dead-lettered, or
  when an event reaches no audit row.
- A deployment with more than one API process would need the demo facts moved to shared storage
  before running the guarded journey there (not needed for compose or the demo today).
- Running the journeys on the Coolify demo (`@staging`) needs the `approvals-seed` one-shot there; left
  for later.
