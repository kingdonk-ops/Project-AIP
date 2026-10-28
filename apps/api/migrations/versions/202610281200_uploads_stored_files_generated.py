"""uploads_stored_files_generated

UPLOADS-08 step 1: ``stored_files`` also holds worker-made files (a report PDF, an export).

- ``source`` (``upload`` | ``generated``), display-only ``filename``, ``purpose`` and
  ``idempotency_key`` columns; a partial unique index on ``(tenant_id, idempotency_key)`` so a
  retried job finds the file it already stored.
- ``project_id`` and ``uploaded_by`` become nullable for generated files only (a tenant-level report
  has no project, a system render no user); an upload still needs both (CHECK). The ACCESS-03
  project-scope policy already treats a NULL project as visible to system/tenant-wide principals.
- Existing rows take their session's ``declared_filename``.

Revision ID: 202610281200
Revises: 202610261200
Create Date: 2026-10-28 12:00:00+00:00
"""

from alembic import op

revision: str = "202610281200"
down_revision: str | None = "202610261200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE stored_files
      ADD COLUMN source text NOT NULL DEFAULT 'upload',
      ADD COLUMN filename text NULL,
      ADD COLUMN purpose text NULL,
      ADD COLUMN idempotency_key text NULL,
      ALTER COLUMN project_id DROP NOT NULL,
      ALTER COLUMN uploaded_by DROP NOT NULL,
      ADD CONSTRAINT ck_stored_files_source CHECK (source IN ('upload', 'generated')),
      ADD CONSTRAINT ck_stored_files_upload_owner
        CHECK (source = 'generated' OR (project_id IS NOT NULL AND uploaded_by IS NOT NULL));

    CREATE UNIQUE INDEX uq_stored_files_tenant_id_idempotency_key
      ON stored_files (tenant_id, idempotency_key)
      WHERE idempotency_key IS NOT NULL;

    UPDATE stored_files f
       SET filename = s.declared_filename
      FROM upload_sessions s
     WHERE s.file_id = f.id AND s.tenant_id = f.tenant_id AND f.filename IS NULL;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
