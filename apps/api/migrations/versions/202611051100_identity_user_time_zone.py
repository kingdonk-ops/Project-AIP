"""identity_user_time_zone

IDENTITY-11 (ADR 0025 consequence): each user's preferred IANA time zone, so emails and pages can
show times in it (PORTAL-12 first). ``app_user.time_zone`` is nullable: ``NULL`` means "no
preference" and clients fall back to the device zone. The name is validated in the application
against ``zoneinfo.available_timezones()`` (``PATCH /api/v1/me``); the database only bounds its
shape, so a tzdata update that adds a zone needs no migration. The row stays tenant-scoped by the
existing ``app_user`` RLS policy; ``aip_app`` already holds UPDATE on the table.

Revision ID: 202611051100
Revises: 202611051000
Create Date: 2026-11-05 11:00:00+00:00
"""

from alembic import op

revision: str = "202611051100"
down_revision: str | None = "202611051000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE app_user
      ADD COLUMN time_zone text NULL,
      ADD CONSTRAINT ck_app_user_time_zone
        CHECK (time_zone IS NULL OR time_zone ~ '^[A-Za-z][A-Za-z0-9_+/-]{0,63}$');
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
