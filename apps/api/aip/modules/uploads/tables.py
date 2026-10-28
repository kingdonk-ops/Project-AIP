"""SQLAlchemy Core declaration for ``upload_sessions`` (UPLOADS-01, ADR 0002).

Created only by the Alembic revision ``202610151200_uploads_sessions``; ``aip-db check-schema``
compares this declaration with the migrated database. The table is tenant-scoped with soft delete
and FORCE ROW LEVEL SECURITY, and ``aip_app`` has no DELETE (deletes are soft).

One row per requested upload. It covers both the ordinary single-part presigned POST and the
resumable multipart upload (UPLOADS-03): the choice lives in ``mode``/``s3_upload_id`` so neither
needs a schema change (data-model note). ``file_id`` is nullable with no FK yet — UPLOADS-02 adds
``stored_files`` and the FK when a scanned object is released.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, Integer, Numeric, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from aip.platform.db.metadata import metadata

upload_sessions = Table(
    "upload_sessions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("requested_by", UUID(as_uuid=True), nullable=False),
    Column("declared_filename", Text, nullable=False),
    Column("declared_mime", Text, nullable=False),
    Column("declared_size_bytes", Numeric, nullable=False),
    Column("mode", Text, nullable=False),
    Column("s3_upload_id", Text, nullable=True),
    Column("quarantine_key", Text, nullable=False),
    Column("chunk_size", Integer, nullable=True),
    Column("parts_received", JSONB, nullable=True),
    Column("client_file_hash", Text, nullable=True),
    Column("status", Text, nullable=False),
    Column("reject_reason", Text, nullable=True),
    Column("priority", Integer, nullable=False, server_default=text("0")),
    Column("client_request_id", UUID(as_uuid=True), nullable=True),
    Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
    Column("file_id", UUID(as_uuid=True), nullable=True),
    Column("sync_version", Integer, nullable=False, server_default=text("1")),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)

# UPLOADS-02: a released, scanned file. Created only by the scan pipeline's ``release`` step, never
# by a request. Tenant-scoped with soft delete and FORCE RLS; ``aip_app`` has no DELETE.
# UPLOADS-08: also a worker-made file (``source = 'generated'``, via ``store_generated_file``), which
# may have no project or user; an upload keeps both (CHECK in the revision).
stored_files = Table(
    "stored_files",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("project_id", UUID(as_uuid=True), nullable=True),
    Column("uploaded_by", UUID(as_uuid=True), nullable=True),
    Column("scan_status", Text, nullable=False),  # quarantined | clean | failed
    Column("preview_status", Text, nullable=False),  # pending | ready | none | failed
    Column("detected_mime", Text, nullable=False),
    Column("size_bytes", Numeric, nullable=False),
    Column("sha256", Text, nullable=False),
    Column("storage_key", Text, nullable=False),
    Column("legal_hold", Boolean, nullable=False, server_default=text("false")),
    # upload | generated
    Column("source", Text, nullable=False, server_default=text("'upload'")),
    Column("filename", Text, nullable=True),  # display-only, never a path
    Column("purpose", Text, nullable=True),  # report | import | export | ...
    Column("idempotency_key", Text, nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)

# UPLOADS-02: one row per scan stage, append-only. ``aip_app`` may INSERT and SELECT but never
# UPDATE/DELETE/TRUNCATE (evidence cannot be altered), enforced by the revision's REVOKE.
scan_results = Table(
    "scan_results",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("session_id", UUID(as_uuid=True), nullable=False),
    Column("file_id", UUID(as_uuid=True), nullable=True),
    Column("stage", Text, nullable=False),  # size_cap | magic_bytes | ratio_cap | clamav | rescan
    Column("outcome", Text, nullable=False),  # pass | fail | error
    Column("signature_db_version", Text, nullable=True),
    Column("detail", JSONB, nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
)
