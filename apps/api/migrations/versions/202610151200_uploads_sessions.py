"""uploads_sessions

UPLOADS-01: ``upload_sessions`` is the only way a file enters the platform. One row per requested
upload, from ``db/templates/tenant_table.sql.tpl`` (uuid PK, tenant_id, timestamps, soft delete,
FORCE RLS with the fail-closed NULLIF policy). Deletes are soft, so ``aip_app`` loses the
template's DELETE grant.

``mode`` and ``status`` are constrained to their known values; ``client_request_id`` is the offline
queue's idempotency key, unique per (tenant, requester) among the rows that carry one. ``file_id``
is nullable with no FK yet — UPLOADS-02 adds ``stored_files`` and the FK on release.

Revision ID: 202610151200
Revises: 202610150900
Create Date: 2026-10-15 12:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610151200"
down_revision: str | None = "202610150900"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="upload_sessions",
            columns=(
                "project_id uuid NOT NULL, requested_by uuid NOT NULL, "
                "declared_filename text NOT NULL, declared_mime text NOT NULL, "
                "declared_size_bytes numeric NOT NULL, mode text NOT NULL, "
                "s3_upload_id text NULL, quarantine_key text NOT NULL, "
                "chunk_size integer NULL, parts_received jsonb NULL, "
                "client_file_hash text NULL, status text NOT NULL, "
                "reject_reason text NULL, priority integer NOT NULL DEFAULT 0, "
                "client_request_id uuid NULL, expires_at timestamptz NOT NULL, "
                "file_id uuid NULL, sync_version integer NOT NULL DEFAULT 1"
            ),
        )
    )
    op.execute("""
    ALTER TABLE upload_sessions
      ADD CONSTRAINT ck_upload_sessions_mode CHECK (mode IN ('single', 'multipart')),
      ADD CONSTRAINT ck_upload_sessions_status CHECK (status IN (
        'requested', 'uploading', 'uploaded', 'scanning', 'validating',
        'released', 'rejected', 'expired', 'aborted')),
      ADD CONSTRAINT ck_upload_sessions_declared_size CHECK (declared_size_bytes > 0),
      ADD CONSTRAINT ck_upload_sessions_priority CHECK (priority >= 0),
      ADD CONSTRAINT ck_upload_sessions_sync_version CHECK (sync_version >= 1);

    -- Idempotency: a repeated client_request_id from the offline queue returns the same session.
    CREATE UNIQUE INDEX uq_upload_sessions_client_request_id
      ON upload_sessions (tenant_id, requested_by, client_request_id)
      WHERE client_request_id IS NOT NULL;

    -- Cleanup of stale requested sessions, and a per-user newest-first listing.
    CREATE INDEX ix_upload_sessions_tenant_status_expires
      ON upload_sessions (tenant_id, status, expires_at);
    CREATE INDEX ix_upload_sessions_tenant_requested_by_created
      ON upload_sessions (tenant_id, requested_by, created_at DESC);

    REVOKE DELETE ON upload_sessions FROM aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
