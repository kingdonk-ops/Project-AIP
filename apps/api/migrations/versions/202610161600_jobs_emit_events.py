"""jobs_emit_events

OPS-03 (ADR 0003, ADR 0030 amendment 2026-10-16): the worker role ``aip_jobs`` may INSERT into
``domain_events``, so a job's final status and its ``job.completed``/``job.failed`` event (and any
event a job handler emits) commit in one transaction. RLS still binds every insert to the job's
tenant (``tenant_isolation`` applies to every role), and the table's write-once trigger still
forbids changing an event after it is written. ``aip_jobs`` keeps no DELETE.

Revision ID: 202610161600
Revises: 202610161300
Create Date: 2026-10-16 16:00:00+00:00
"""

from alembic import op

revision: str = "202610161600"
down_revision: str | None = "202610161300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT INSERT ON domain_events TO aip_jobs;")


def downgrade() -> None:
    raise NotImplementedError("forward-only")
