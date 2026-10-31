"""forms_supervisor_review

FORMS-10 (ADR 0041 §5): ``form_templates`` gains ``has_supervisor_review``, whether inspections of
the template go to supervisor review before Performed. Existing templates keep the default
``true``. INSPECTIONS-10 copies the value onto an inspection when it is created, so changing it
later never changes inspections that already exist.

Revision ID: 202611011300
Revises: 202610311800
Create Date: 2026-11-01 13:00:00+00:00
"""

from alembic import op

revision: str = "202611011300"
down_revision: str | None = "202610311800"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE form_templates ADD COLUMN has_supervisor_review boolean NOT NULL DEFAULT true;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
