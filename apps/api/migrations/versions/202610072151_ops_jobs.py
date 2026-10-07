"""ops_jobs

OPS-01: user-visible job records. Procrastinate (OPS-02, ADR 0003) owns queue transport; ``jobs``
is the business record the Jobs API reads, ``job_events`` its append-only state history.

Written by hand to the ADR 0002 tenant-table rules (``db/templates/`` does not exist yet;
DATABASE-02 adds it): uuid PK generated in the app (UUIDv7), ``tenant_id``, timestamps, soft
delete on ``jobs`` only, FORCE ROW LEVEL SECURITY with a fail-closed tenant policy.

Grants go to the DATABASE-02 roles ``aip_app`` and ``aip_jobs`` only when those roles exist
(they are created by the cluster bootstrap, outside migrations). A database migrated before the
roles exist gets no grants and must be re-granted; see the OPS-01 notes on the board.

Revision ID: 202610072151
Revises: 202610071200
Create Date: 2026-10-07 21:51:40.000000+00:00
"""

from alembic import op

revision: str = "202610072151"
down_revision: str | None = "202610071200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE jobs (
      id uuid PRIMARY KEY,
      tenant_id uuid NOT NULL,
      job_type text NOT NULL,
      status text NOT NULL DEFAULT 'queued',
      idempotency_key text,
      correlation_id uuid NOT NULL,
      attempts integer NOT NULL DEFAULT 0,
      payload jsonb NOT NULL DEFAULT '{}'::jsonb,
      result_ref text,
      error text,
      requested_by uuid,
      procrastinate_job_id bigint,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      deleted_at timestamptz,
      CONSTRAINT uq_jobs_id_tenant_id UNIQUE (id, tenant_id),
      CONSTRAINT ck_jobs_status
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
      CONSTRAINT ck_jobs_attempts CHECK (attempts >= 0),
      CONSTRAINT ck_jobs_job_type CHECK (job_type <> ''),
      CONSTRAINT ck_jobs_idempotency_key CHECK (idempotency_key <> '')
    );

    CREATE UNIQUE INDEX uq_jobs_tenant_id_job_type_idempotency_key
      ON jobs (tenant_id, job_type, idempotency_key)
      WHERE idempotency_key IS NOT NULL;
    CREATE INDEX ix_jobs_tenant_id_status ON jobs (tenant_id, status) WHERE deleted_at IS NULL;
    CREATE INDEX ix_jobs_tenant_id_requested_by_created_at
      ON jobs (tenant_id, requested_by, created_at DESC) WHERE deleted_at IS NULL;
    CREATE INDEX ix_jobs_correlation_id ON jobs (correlation_id);

    ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
    ALTER TABLE jobs FORCE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON jobs
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
    """)
    op.execute("""
    CREATE TABLE job_events (
      id uuid PRIMARY KEY,
      tenant_id uuid NOT NULL,
      job_id uuid NOT NULL,
      seq integer NOT NULL,
      from_status text,
      to_status text NOT NULL,
      detail jsonb NOT NULL DEFAULT '{}'::jsonb,
      occurred_at timestamptz NOT NULL DEFAULT now(),
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
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

    -- Append-only: nobody but the owner may rewrite history.
    REVOKE UPDATE, DELETE, TRUNCATE ON job_events FROM PUBLIC;
    """)
    op.execute("""
    DO $grants$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aip_app') THEN
        GRANT SELECT, INSERT ON jobs TO aip_app;
        GRANT UPDATE (status, attempts, result_ref, error, procrastinate_job_id, updated_at,
                      deleted_at)
          ON jobs TO aip_app;
        GRANT SELECT, INSERT ON job_events TO aip_app;
      ELSE
        RAISE NOTICE 'role aip_app does not exist yet: jobs grants skipped';
      END IF;

      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aip_jobs') THEN
        GRANT SELECT ON jobs TO aip_jobs;
        GRANT UPDATE (status, attempts, result_ref, error, procrastinate_job_id, updated_at)
          ON jobs TO aip_jobs;
        GRANT SELECT, INSERT ON job_events TO aip_jobs;
      ELSE
        RAISE NOTICE 'role aip_jobs does not exist yet: jobs grants skipped';
      END IF;
    END
    $grants$;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
