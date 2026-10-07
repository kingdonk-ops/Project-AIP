"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from alembic import op

revision: str = ${repr(up_revision).replace("'", '"')}
down_revision: str | None = ${repr(down_revision).replace("'", '"')}
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    -- raw SQL here (templates: db/templates/)
    SELECT 1;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
