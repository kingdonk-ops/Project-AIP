"""uploads_stored_files_scan

UPLOADS-02 step 1: the scan pipeline's tables.

- ``stored_files`` (tenant table, soft delete, FORCE RLS): a released, scanned file. Extra columns
  beyond the template, plus the ``scan_status``/``preview_status`` check constraints, a
  ``legal_hold`` default, and a ``(id, tenant_id)`` unique so the session FK is tenant-safe.
- ``scan_results`` (append-only): one row per scan stage. ``aip_app`` keeps SELECT/INSERT but loses
  UPDATE/DELETE/TRUNCATE, so recorded evidence can never be altered (data-model note).
- ``upload_sessions.file_id`` gains its tenant-safe FK to ``stored_files`` (promised in UPLOADS-01).

Revision ID: 202610251400
Revises: 202610251200
Create Date: 2026-10-25 14:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610251400"
down_revision: str | None = "202610251200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="stored_files",
            columns=(
                "project_id uuid NOT NULL, uploaded_by uuid NOT NULL, "
                "scan_status text NOT NULL, preview_status text NOT NULL, "
                "detected_mime text NOT NULL, size_bytes numeric NOT NULL, "
                "sha256 text NOT NULL, storage_key text NOT NULL, legal_hold boolean NOT NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE stored_files
      ALTER COLUMN legal_hold SET DEFAULT false,
      ADD CONSTRAINT ck_stored_files_scan_status
        CHECK (scan_status IN ('quarantined', 'clean', 'failed')),
      ADD CONSTRAINT ck_stored_files_preview_status
        CHECK (preview_status IN ('pending', 'ready', 'none', 'failed')),
      ADD CONSTRAINT uq_stored_files_id_tenant_id UNIQUE (id, tenant_id);

    -- Tenant-safe: a session can only point at a released file in its own tenant.
    ALTER TABLE upload_sessions
      ADD CONSTRAINT fk_upload_sessions_file_id
      FOREIGN KEY (file_id, tenant_id) REFERENCES stored_files (id, tenant_id);
    """)

    # A released file belongs to a project (ACCESS-03): a project-scoped user may see only the files
    # on a project they hold. This RESTRICTIVE policy ANDs with tenant isolation and also creates
    # ix_stored_files_tenant_id_project_id, so no separate index is declared above.
    op.execute(render_template("project_scoped_policy", table="stored_files"))

    # scan_results is append-only and not partitioned: one short-lived row per stage per upload,
    # low volume, so it needs no monthly partitioning. RLS fails closed exactly as the templates do.
    op.execute("""
    CREATE TABLE scan_results (
      id uuid NOT NULL,
      tenant_id uuid NOT NULL,
      session_id uuid NOT NULL,
      file_id uuid NULL,
      stage text NOT NULL,
      outcome text NOT NULL,
      signature_db_version text NULL,
      detail jsonb NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT pk_scan_results PRIMARY KEY (id),
      CONSTRAINT ck_scan_results_stage
        CHECK (stage IN ('size_cap', 'magic_bytes', 'ratio_cap', 'clamav', 'rescan')),
      CONSTRAINT ck_scan_results_outcome CHECK (outcome IN ('pass', 'fail', 'error'))
    );

    CREATE INDEX ix_scan_results_tenant_id ON scan_results (tenant_id);
    CREATE INDEX ix_scan_results_tenant_id_session_id ON scan_results (tenant_id, session_id);

    ALTER TABLE scan_results ENABLE ROW LEVEL SECURITY;
    ALTER TABLE scan_results FORCE ROW LEVEL SECURITY;

    CREATE POLICY tenant_isolation ON scan_results
      FOR ALL
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

    REVOKE UPDATE, DELETE, TRUNCATE ON scan_results FROM aip_app, aip_jobs, aip_readonly;
    GRANT SELECT, INSERT ON scan_results TO aip_app;
    GRANT SELECT ON scan_results TO aip_readonly;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
