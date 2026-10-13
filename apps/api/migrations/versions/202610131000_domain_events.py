"""domain_events

ARCH-05 (ADR 0003): the transactional outbox. Modules write a domain event in the same
``with_tenant`` transaction as the state change; the dispatcher (``aip_jobs``) later marks it
published or dead-lettered.

The table is append-only, so it is written by hand from the tenant-table template without
``updated_at``/``deleted_at`` (like ``job_events``). ``aip_app`` may only INSERT and SELECT;
``aip_jobs`` may SELECT and UPDATE the four publish columns, across tenants, through its own
policies; nobody may DELETE.

Revision ID: 202610131000
Revises: 202610120445
Create Date: 2026-10-13 10:00:00+00:00
"""

from alembic import op

revision: str = "202610131000"
down_revision: str | None = "202610120445"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE domain_events (
      id uuid NOT NULL,
      tenant_id uuid NOT NULL,
      project_id uuid NULL,
      asset_id uuid NULL,
      event_name text NOT NULL,
      event_version integer NOT NULL,
      aggregate_type text NOT NULL,
      aggregate_id uuid NOT NULL,
      payload jsonb NOT NULL,
      actor_id uuid NULL,
      occurred_at timestamptz NOT NULL DEFAULT now(),
      published_at timestamptz NULL,
      attempts integer NOT NULL DEFAULT 0,
      dead_lettered_at timestamptz NULL,
      last_error text NULL,
      CONSTRAINT pk_domain_events PRIMARY KEY (id),
      CONSTRAINT ck_domain_events_event_name CHECK (event_name <> ''),
      CONSTRAINT ck_domain_events_event_version CHECK (event_version >= 1),
      CONSTRAINT ck_domain_events_aggregate_type CHECK (aggregate_type <> ''),
      CONSTRAINT ck_domain_events_attempts CHECK (attempts >= 0)
    );

    -- The dispatcher's claim query: unpublished, live events in order.
    CREATE INDEX ix_domain_events_tenant_id_occurred_at_pending
      ON domain_events (tenant_id, occurred_at)
      WHERE published_at IS NULL AND dead_lettered_at IS NULL;
    CREATE INDEX ix_domain_events_aggregate_type_aggregate_id
      ON domain_events (aggregate_type, aggregate_id);
    CREATE INDEX ix_domain_events_asset_id ON domain_events (asset_id);
    CREATE INDEX ix_domain_events_event_name_occurred_at ON domain_events (event_name, occurred_at);

    ALTER TABLE domain_events ENABLE ROW LEVEL SECURITY;
    ALTER TABLE domain_events FORCE ROW LEVEL SECURITY;

    CREATE POLICY tenant_isolation ON domain_events
      FOR ALL
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

    -- The dispatcher claims events across tenants. Its column grant below limits what it can
    -- change; it has no INSERT or DELETE, so these policies cannot add or remove rows.
    CREATE POLICY dispatcher_select ON domain_events FOR SELECT TO aip_jobs USING (true);
    CREATE POLICY dispatcher_update ON domain_events
      FOR UPDATE TO aip_jobs USING (true) WITH CHECK (true);

    -- Append-only: no runtime role may DELETE an event or rewrite what it says.
    GRANT SELECT, INSERT ON domain_events TO aip_app;
    GRANT SELECT ON domain_events TO aip_jobs;
    GRANT UPDATE (published_at, attempts, dead_lettered_at, last_error)
      ON domain_events TO aip_jobs;
    GRANT SELECT ON domain_events TO aip_readonly;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
