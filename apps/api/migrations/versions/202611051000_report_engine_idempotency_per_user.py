"""report_engine_idempotency_per_user

REPORTS-07 (review 13 L1): a render request's ``Idempotency-Key`` belongs to the user who sent it,
so one user's key never returns another user's job. The tenant-wide ``UNIQUE (tenant_id,
idempotency_key)`` becomes a unique index on ``(tenant_id, requested_by, idempotency_key)`` for
rows that have a key. ``NULLS NOT DISTINCT`` keeps system requests (``requested_by`` NULL, e.g. an
auto-render without an actor) unique per key too. Every existing row still satisfies it: the old
constraint was stricter.

Revision ID: 202611051000
Revises: 202611031000
Create Date: 2026-11-05 10:00:00+00:00
"""

from alembic import op

revision: str = "202611051000"
down_revision: str | None = "202611031000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE UNIQUE INDEX uq_report_render_jobs_tenant_id_requested_by_idempotency_key
      ON report_render_jobs (tenant_id, requested_by, idempotency_key) NULLS NOT DISTINCT
      WHERE idempotency_key IS NOT NULL;
    ALTER TABLE report_render_jobs
      DROP CONSTRAINT uq_report_render_jobs_tenant_id_idempotency_key;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
