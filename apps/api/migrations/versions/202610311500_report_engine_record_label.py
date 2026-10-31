"""report_engine_record_label

REPORTS-04: ``report_render_jobs`` gains ``record_label``, the source record's human label at
request time (for a project ``"<code> <name>"``), so the report register can show and search it
without reading snapshot bodies (up to 5 MB each). Jobs from REPORTS-02 keep ``NULL`` (the page
falls back to the record id). At most 300 characters.

Revision ID: 202610311500
Revises: 202610311200
Create Date: 2026-10-31 15:00:00+00:00
"""

from alembic import op

revision: str = "202610311500"
down_revision: str | None = "202610311200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE report_render_jobs ADD COLUMN record_label text NULL;
    ALTER TABLE report_render_jobs
      ADD CONSTRAINT ck_report_render_jobs_record_label
        CHECK (record_label IS NULL OR char_length(record_label) BETWEEN 1 AND 300);
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
