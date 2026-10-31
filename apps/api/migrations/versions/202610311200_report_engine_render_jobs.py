"""report_engine_render_jobs

REPORTS-02 (ADR 0002, ADR 0003, ADR 0016, ADR 0036 §5): the render job and its pinned data.

- ``report_data_snapshots``: the frozen render input of one record, append-only and hand-written
  like ``workflow_decision_history``. ``data`` is the canonical snapshot body, ``data_hash`` the
  sha256 (hex) of its RFC 8785 JSON and ``size_bytes`` that JSON's length (at most 5 MB).
  ``unique (tenant_id, record_type, record_id, data_hash)``: the same data is snapshotted once.
  No ``updated_at``/``deleted_at``; ``aip_app`` may only SELECT and INSERT, and UPDATE, DELETE and
  TRUNCATE are revoked from every runtime role. Not range-partitioned: one row per distinct render
  input is low volume, and a partition key would stop render jobs referencing it (the ADR 0031
  reasoning for ``audit_log``).
- ``report_render_jobs``: one row per render request from ``tenant_table``, pinned to a template
  version (``(template_id, tenant_id)`` -> ``report_templates``, which gains ``unique (id,
  tenant_id)`` here) and a snapshot. ``status`` moves ``queued -> running -> succeeded|failed``; a
  succeeded row always names its stored file and the file's sha256. ``rerender_of`` names the
  first job of a re-render chain, so a re-render reproduces that job's document. ``file_id`` is
  the uploads stored file (no FK across modules); ``ops_job_id`` the OPS-01 ``jobs`` row.
- Both carry ``project_id`` and copy the ACCESS-03 project-scope policy.

Handlers run on the ``aip_app`` engine (OPS-17 option (a)), so ``aip_jobs`` gains nothing.

Revision ID: 202610311200
Revises: 202610291000
Create Date: 2026-10-31 12:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610311200"
down_revision: str | None = "202610291000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE report_templates
      ADD CONSTRAINT uq_report_templates_id_tenant_id UNIQUE (id, tenant_id);

    CREATE TABLE report_data_snapshots (
      id uuid NOT NULL,
      tenant_id uuid NOT NULL,
      record_type text NOT NULL,
      record_id uuid NOT NULL,
      record_version integer NULL,
      project_id uuid NULL,
      schema_version integer NOT NULL DEFAULT 1,
      data jsonb NOT NULL,
      data_hash text NOT NULL,
      size_bytes integer NOT NULL,
      created_by uuid NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT pk_report_data_snapshots PRIMARY KEY (id),
      CONSTRAINT uq_report_data_snapshots_id_tenant_id UNIQUE (id, tenant_id),
      CONSTRAINT uq_report_data_snapshots_record_data_hash
        UNIQUE (tenant_id, record_type, record_id, data_hash),
      CONSTRAINT fk_report_data_snapshots_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      CONSTRAINT ck_report_data_snapshots_data_hash CHECK (data_hash ~ '^[0-9a-f]{64}$'),
      CONSTRAINT ck_report_data_snapshots_size_bytes
        CHECK (size_bytes >= 0 AND size_bytes <= 5242880),
      CONSTRAINT ck_report_data_snapshots_schema_version CHECK (schema_version >= 1)
    );

    CREATE INDEX ix_report_data_snapshots_tenant_id ON report_data_snapshots (tenant_id);
    CREATE INDEX ix_report_data_snapshots_tenant_id_record_created_at
      ON report_data_snapshots (tenant_id, record_type, record_id, created_at DESC);

    ALTER TABLE report_data_snapshots ENABLE ROW LEVEL SECURITY;
    ALTER TABLE report_data_snapshots FORCE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON report_data_snapshots
      FOR ALL
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

    REVOKE UPDATE, DELETE, TRUNCATE ON report_data_snapshots
      FROM PUBLIC, aip_app, aip_jobs, aip_readonly;
    GRANT SELECT, INSERT ON report_data_snapshots TO aip_app;
    GRANT SELECT ON report_data_snapshots TO aip_readonly;
    """)
    op.execute(render_template("project_scoped_policy", table="report_data_snapshots"))

    op.execute(
        render_template(
            "tenant_table",
            table="report_render_jobs",
            columns=(
                "template_id uuid NOT NULL, template_key text NOT NULL, "
                "template_version integer NOT NULL, variant text NOT NULL, "
                "record_type text NOT NULL, record_id uuid NOT NULL, project_id uuid NULL, "
                "snapshot_id uuid NOT NULL, data_hash text NOT NULL, status text NOT NULL, "
                "ops_job_id uuid NULL, idempotency_key text NULL, trigger_event_id uuid NULL, "
                "requested_by uuid NULL, rerender_of uuid NULL, html_sha256 text NULL, "
                "file_id uuid NULL, pdf_sha256 text NULL, pdf_size_bytes bigint NULL, "
                "error_code text NULL, rendered_at timestamptz NULL"
            ),
        )
    )
    op.execute(render_template("project_scoped_policy", table="report_render_jobs"))
    op.execute("""
    ALTER TABLE report_render_jobs ALTER COLUMN status SET DEFAULT 'queued';
    ALTER TABLE report_render_jobs
      ADD CONSTRAINT fk_report_render_jobs_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      ADD CONSTRAINT uq_report_render_jobs_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT uq_report_render_jobs_tenant_id_idempotency_key
        UNIQUE (tenant_id, idempotency_key),
      ADD CONSTRAINT fk_report_render_jobs_template
        FOREIGN KEY (template_id, tenant_id) REFERENCES report_templates (id, tenant_id),
      ADD CONSTRAINT fk_report_render_jobs_snapshot
        FOREIGN KEY (snapshot_id, tenant_id) REFERENCES report_data_snapshots (id, tenant_id),
      ADD CONSTRAINT fk_report_render_jobs_rerender_of
        FOREIGN KEY (rerender_of, tenant_id) REFERENCES report_render_jobs (id, tenant_id),
      ADD CONSTRAINT ck_report_render_jobs_status
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
      ADD CONSTRAINT ck_report_render_jobs_variant
        CHECK (variant IN ('internal', 'client', 'certificate')),
      ADD CONSTRAINT ck_report_render_jobs_data_hash CHECK (data_hash ~ '^[0-9a-f]{64}$'),
      ADD CONSTRAINT ck_report_render_jobs_html_sha256
        CHECK (html_sha256 IS NULL OR html_sha256 ~ '^[0-9a-f]{64}$'),
      ADD CONSTRAINT ck_report_render_jobs_pdf_sha256
        CHECK (pdf_sha256 IS NULL OR pdf_sha256 ~ '^[0-9a-f]{64}$'),
      ADD CONSTRAINT ck_report_render_jobs_idempotency_key
        CHECK (idempotency_key IS NULL OR char_length(idempotency_key) BETWEEN 1 AND 200),
      ADD CONSTRAINT ck_report_render_jobs_succeeded
        CHECK (status <> 'succeeded' OR (file_id IS NOT NULL AND pdf_sha256 IS NOT NULL));

    CREATE INDEX ix_report_render_jobs_tenant_id_status_created_at
      ON report_render_jobs (tenant_id, status, created_at);
    CREATE INDEX ix_report_render_jobs_tenant_id_record_created_at
      ON report_render_jobs (tenant_id, record_type, record_id, created_at DESC);

    REVOKE DELETE ON report_render_jobs FROM aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
