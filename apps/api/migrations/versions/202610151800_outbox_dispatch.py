"""outbox_dispatch

ARCH-07 (ADR 0003, ADR 0030): what the outbox dispatcher and the dead-letter queue need on
``domain_events``.

- ``next_attempt_at``: when a failed event may be tried again (backoff). ``aip_jobs`` may now
  UPDATE it as well as the four publish columns.
- ``discarded_at``, ``discarded_by``, ``discard_reason``: an operator's decision to drop a
  dead-lettered event. Written only by ``outbox_discard``; a reason is mandatory.
- ``last_error`` is bounded (4000 characters); the dispatcher truncates before writing.
- Write-once: once ``published_at`` or ``discarded_at`` is set, no role (not even a SECURITY
  DEFINER function) may change or clear it (``domain_events_write_once`` trigger).
- The dispatcher's partial index becomes ``(next_attempt_at NULLS FIRST, occurred_at)`` over
  unpublished, live events; a second partial index serves the per-tenant dead-letter counts.
- Three ``SECURITY DEFINER`` functions owned by ``aip_owner``, ``EXECUTE`` to ``aip_app`` only, for
  the ``platform.events.manage``-gated dead-letter API: ``outbox_dead_letters`` lists dead-lettered
  events across tenants (never a payload), ``outbox_retry`` puts one back in the queue and
  ``outbox_discard`` drops one with a reason. ``aip_owner`` already reads every tenant's events
  (``platform_counts_owner_read``); a matching ``FOR UPDATE TO aip_owner`` policy lets these
  functions, and nothing else, change them.

Revision ID: 202610151800
Revises: 202610151500
Create Date: 2026-10-15 18:00:00+00:00
"""

from alembic import op

revision: str = "202610151800"
down_revision: str | None = "202610151500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE domain_events
      ADD COLUMN next_attempt_at timestamptz NULL,
      ADD COLUMN discarded_at timestamptz NULL,
      ADD COLUMN discarded_by uuid NULL,
      ADD COLUMN discard_reason text NULL,
      ADD CONSTRAINT ck_domain_events_last_error CHECK (char_length(last_error) <= 4000),
      ADD CONSTRAINT ck_domain_events_discard_reason CHECK (
        char_length(discard_reason) <= 1000
        AND (discarded_at IS NULL OR btrim(coalesce(discard_reason, '')) <> '')
      );

    DROP INDEX ix_domain_events_tenant_id_occurred_at_pending;
    CREATE INDEX ix_domain_events_pending
      ON domain_events (next_attempt_at NULLS FIRST, occurred_at)
      WHERE published_at IS NULL AND dead_lettered_at IS NULL;
    CREATE INDEX ix_domain_events_tenant_id_dead_letter
      ON domain_events (tenant_id)
      WHERE dead_lettered_at IS NOT NULL AND discarded_at IS NULL;

    GRANT UPDATE (next_attempt_at) ON domain_events TO aip_jobs;

    -- Write-once publish and discard columns (PR #55 review): a published or discarded event
    -- stays that way, whoever runs the UPDATE.
    CREATE FUNCTION domain_events_write_once() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, public
    AS $fn$
    BEGIN
      IF OLD.published_at IS NOT NULL
         AND NEW.published_at IS DISTINCT FROM OLD.published_at THEN
        RAISE EXCEPTION 'domain_events.published_at is write-once' USING ERRCODE = '55000';
      END IF;
      IF OLD.discarded_at IS NOT NULL AND (
           NEW.discarded_at IS DISTINCT FROM OLD.discarded_at
           OR NEW.discarded_by IS DISTINCT FROM OLD.discarded_by
           OR NEW.discard_reason IS DISTINCT FROM OLD.discard_reason) THEN
        RAISE EXCEPTION 'domain_events discard columns are write-once' USING ERRCODE = '55000';
      END IF;
      RETURN NEW;
    END;
    $fn$;
    REVOKE ALL ON FUNCTION domain_events_write_once() FROM PUBLIC;
    CREATE TRIGGER domain_events_write_once
      BEFORE UPDATE ON domain_events
      FOR EACH ROW EXECUTE FUNCTION domain_events_write_once();

    -- Only the dead-letter functions below run as aip_owner; permissive policies are OR'd, so
    -- this does not loosen any runtime role's isolation.
    CREATE POLICY outbox_owner_update ON domain_events
      FOR UPDATE TO aip_owner USING (true) WITH CHECK (true);
    """)
    # contract: 202610151800 - SECURITY DEFINER on purpose (ARCH-07): the cross-tenant dead-letter
    # queue for platform operators. Owned by aip_owner, fixed search_path, EXECUTE to aip_app only
    # (the routes are gated by platform.events.manage). The list never returns a payload, project,
    # aggregate or actor; retry and discard touch only dead-lettered, unpublished, undiscarded rows
    # and only the dispatch columns.
    op.execute("""
    CREATE FUNCTION outbox_dead_letters(lim integer, after uuid)
    RETURNS TABLE (
      id uuid, tenant_id uuid, event_name text, event_version integer, attempts integer,
      last_error text, dead_lettered_at timestamptz
    )
    LANGUAGE sql
    STABLE
    SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $fn$
      SELECT d.id, d.tenant_id, d.event_name, d.event_version, d.attempts, d.last_error,
             d.dead_lettered_at
      FROM public.domain_events AS d
      WHERE d.dead_lettered_at IS NOT NULL
        AND d.discarded_at IS NULL
        AND d.published_at IS NULL
        AND (after IS NULL OR d.id > after)
      ORDER BY d.id
      LIMIT least(greatest(coalesce(lim, 50), 1), 500);
    $fn$;

    CREATE FUNCTION outbox_retry(event_id uuid)
    RETURNS TABLE (event_name text, event_version integer)
    LANGUAGE sql
    SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $fn$
      UPDATE public.domain_events AS d
         SET dead_lettered_at = NULL, attempts = 0, next_attempt_at = NULL
       WHERE d.id = event_id
         AND d.dead_lettered_at IS NOT NULL
         AND d.discarded_at IS NULL
         AND d.published_at IS NULL
      RETURNING d.event_name, d.event_version;
    $fn$;

    CREATE FUNCTION outbox_discard(event_id uuid, reason text, actor uuid)
    RETURNS TABLE (event_name text, event_version integer)
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $fn$
    BEGIN
      IF reason IS NULL OR btrim(reason) = '' THEN
        RAISE EXCEPTION 'a discard reason is required' USING ERRCODE = '22023';
      END IF;
      RETURN QUERY
      UPDATE public.domain_events AS d
         SET discarded_at = now(), discarded_by = actor, discard_reason = btrim(reason)
       WHERE d.id = event_id
         AND d.dead_lettered_at IS NOT NULL
         AND d.discarded_at IS NULL
         AND d.published_at IS NULL
      RETURNING d.event_name, d.event_version;
    END;
    $fn$;

    REVOKE ALL ON FUNCTION outbox_dead_letters(integer, uuid) FROM PUBLIC;
    REVOKE ALL ON FUNCTION outbox_retry(uuid) FROM PUBLIC;
    REVOKE ALL ON FUNCTION outbox_discard(uuid, text, uuid) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION outbox_dead_letters(integer, uuid) TO aip_app;
    GRANT EXECUTE ON FUNCTION outbox_retry(uuid) TO aip_app;
    GRANT EXECUTE ON FUNCTION outbox_discard(uuid, text, uuid) TO aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
