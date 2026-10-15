"""event_catalogue

ARCH-06: the global event-catalogue status table and the cross-tenant counts function.

- ``platform_event_status``: one row per deprecated ``(event_name, event_version)``. Global
  reference data (no ``tenant_id``, no RLS), like ``permission``; it holds no tenant data, only the
  catalogue's own deprecation flag. On the global-table allow-list. ``aip_app`` may SELECT, INSERT
  and UPDATE it (the deprecate endpoint, gated by ``platform.events.manage``); ``aip_readonly`` may
  SELECT.
- ``platform_event_counts(since timestamptz)``: a ``SECURITY DEFINER`` function owned by
  ``aip_owner`` returning only ``(event_name, event_version, published, failed)`` aggregates of
  ``domain_events`` across every tenant since ``since`` — never a payload. ``domain_events`` forces
  RLS and ``aip_owner`` is ``NOBYPASSRLS``, so a permissive ``FOR SELECT TO aip_owner`` policy lets
  the function (and only it) read every tenant's rows. ``EXECUTE`` is granted to ``aip_app`` so the
  catalogue API can read the health figures without seeing another tenant's events.

Revision ID: 202610150900
Revises: 202610141200
Create Date: 2026-10-15 09:00:00+00:00
"""

from alembic import op

revision: str = "202610150900"
down_revision: str | None = "202610141200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE platform_event_status (
      event_name text NOT NULL,
      event_version integer NOT NULL,
      status text NOT NULL DEFAULT 'active',
      deprecated_at timestamptz NULL,
      deprecated_by uuid NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT pk_platform_event_status PRIMARY KEY (event_name, event_version),
      CONSTRAINT ck_platform_event_status_event_name CHECK (event_name <> ''),
      CONSTRAINT ck_platform_event_status_event_version CHECK (event_version >= 1),
      CONSTRAINT ck_platform_event_status_status CHECK (status IN ('active', 'deprecated')),
      CONSTRAINT ck_platform_event_status_deprecated CHECK (
        (status = 'deprecated') = (deprecated_at IS NOT NULL)
      )
    );
    REVOKE ALL ON TABLE platform_event_status FROM PUBLIC;
    GRANT SELECT, INSERT, UPDATE ON platform_event_status TO aip_app;
    GRANT SELECT ON platform_event_status TO aip_readonly;

    -- Let the SECURITY DEFINER counts function (owned by aip_owner) read every tenant's events.
    -- domain_events FORCES RLS and aip_owner is NOBYPASSRLS, so without this policy the owner sees
    -- nothing. aip_owner runs no runtime queries except this function, which returns aggregates
    -- only. Permissive policies are OR'd, so this does not loosen any runtime role's isolation.
    CREATE POLICY platform_counts_owner_read ON domain_events
      FOR SELECT TO aip_owner USING (true);
    """)
    # contract: 202610150900 - SECURITY DEFINER on purpose (ARCH-06): the cross-tenant read path for
    # the event catalogue, owned by aip_owner, fixed search_path, STABLE, returns only per-event
    # aggregate counts (never a payload, tenant_id, actor or id). EXECUTE granted to aip_app only.
    op.execute("""
    CREATE FUNCTION platform_event_counts(since timestamptz)
    RETURNS TABLE (event_name text, event_version integer, published bigint, failed bigint)
    LANGUAGE sql
    STABLE
    SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $fn$
      SELECT d.event_name, d.event_version,
             count(*) FILTER (WHERE d.published_at IS NOT NULL) AS published,
             count(*) FILTER (WHERE d.dead_lettered_at IS NOT NULL) AS failed
      FROM public.domain_events AS d
      WHERE d.occurred_at >= since
      GROUP BY d.event_name, d.event_version;
    $fn$;
    REVOKE ALL ON FUNCTION platform_event_counts(timestamptz) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION platform_event_counts(timestamptz) TO aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
