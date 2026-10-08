"""ops_jobs

OPS-01: user-visible job records. Procrastinate (OPS-02, ADR 0003) owns queue transport; ``jobs``
is the business record the Jobs API reads, ``job_events`` its append-only state history.

``jobs`` comes from ``db/templates/tenant_table.sql.tpl`` (uuid PK, tenant_id, timestamps, soft
delete, FORCE RLS with the fail-closed NULLIF policy, grants to aip_app and aip_readonly). The
template's column list allows no quotes, so string defaults and CHECK constraints are added after.

``job_events`` is append-only, so it is written by hand with the same policy but without
``updated_at``/``deleted_at``, and no role is granted UPDATE or DELETE on it.

The runtime roles exist before migrations run (cluster bootstrap, ADR 0012), so grants are plain.

Revision ID: 202610080510
Revises: 202610072200
Create Date: 2026-10-08 05:10:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610080510"
down_revision: str | None = "202610072200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="jobs",
            columns=(
                "job_type text NOT NULL, status text NOT NULL, idempotency_key text NULL, "
                "correlation_id uuid NOT NULL, attempts integer NOT NULL DEFAULT 0, "
                "payload jsonb NOT NULL, result_ref text NULL, error text NULL, "
                "requested_by uuid NULL, procrastinate_job_id bigint NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE jobs ALTER COLUMN status SET DEFAULT 'queued';
    ALTER TABLE jobs ALTER COLUMN payload SET DEFAULT '{}'::jsonb;
    ALTER TABLE jobs
      ADD CONSTRAINT uq_jobs_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT ck_jobs_status
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
      ADD CONSTRAINT ck_jobs_attempts CHECK (attempts >= 0),
      ADD CONSTRAINT ck_jobs_job_type CHECK (job_type <> ''),
      ADD CONSTRAINT ck_jobs_idempotency_key CHECK (idempotency_key <> '');

    CREATE UNIQUE INDEX uq_jobs_tenant_id_job_type_idempotency_key
      ON jobs (tenant_id, job_type, idempotency_key)
      WHERE idempotency_key IS NOT NULL;
    CREATE INDEX ix_jobs_tenant_id_status ON jobs (tenant_id, status) WHERE deleted_at IS NULL;
    CREATE INDEX ix_jobs_tenant_id_requested_by_created_at
      ON jobs (tenant_id, requested_by, created_at DESC) WHERE deleted_at IS NULL;
    CREATE INDEX ix_jobs_correlation_id ON jobs (correlation_id);

    -- The worker (aip_jobs) reads jobs and moves their state; it never creates or rewrites them.
    GRANT SELECT ON jobs TO aip_jobs;
    GRANT UPDATE (status, attempts, result_ref, error, procrastinate_job_id, updated_at)
      ON jobs TO aip_jobs;
    """)
    op.execute("""
    CREATE TABLE job_events (
      id uuid NOT NULL,
      tenant_id uuid NOT NULL,
      job_id uuid NOT NULL,
      seq integer NOT NULL,
      from_status text NULL,
      to_status text NOT NULL,
      detail jsonb NOT NULL DEFAULT '{}'::jsonb,
      occurred_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT pk_job_events PRIMARY KEY (id),
      -- (job_id, tenant_id) so an event can never point at another tenant's job.
      CONSTRAINT fk_job_events_job_id_tenant_id_jobs
        FOREIGN KEY (job_id, tenant_id) REFERENCES jobs (id, tenant_id),
      CONSTRAINT uq_job_events_job_id_seq UNIQUE (job_id, seq),
      CONSTRAINT ck_job_events_seq CHECK (seq >= 1),
      CONSTRAINT ck_job_events_from_status CHECK (
        from_status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')
      ),
      CONSTRAINT ck_job_events_to_status CHECK (
        to_status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')
      )
    );

    CREATE INDEX ix_job_events_tenant_id_occurred_at ON job_events (tenant_id, occurred_at);

    ALTER TABLE job_events ENABLE ROW LEVEL SECURITY;
    ALTER TABLE job_events FORCE ROW LEVEL SECURITY;

    CREATE POLICY tenant_isolation ON job_events
      FOR ALL
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

    -- Append-only: no runtime role may UPDATE or DELETE an event.
    GRANT SELECT, INSERT ON job_events TO aip_app, aip_jobs;
    GRANT SELECT ON job_events TO aip_readonly;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
