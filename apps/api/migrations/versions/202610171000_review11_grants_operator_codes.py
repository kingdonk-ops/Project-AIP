"""review11_grants_operator_codes

Review 11 L1 and L2 (defence in depth).

- L1: ``role_permission`` may never hold an operator-only ``platform.*`` code. ``RoleService``
  already refuses them (ADR 0029); the CHECK holds for any write path that bypasses the service.
- L2: ``aip_app`` loses the hard-DELETE grant that ``db/templates/tenant_table.sql.tpl`` gave
  ``app_user``, ``tenant_membership`` and ``jobs``. The platform soft-deletes, nothing deletes
  these rows, and every later tenant table already revoked DELETE. The template now grants only
  SELECT, INSERT and UPDATE.

Revision ID: 202610171000
Revises: 202610161600
Create Date: 2026-10-17 10:00:00+00:00
"""

from alembic import op

revision: str = "202610171000"
down_revision: str | None = "202610161600"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE role_permission ADD CONSTRAINT ck_role_permission_not_operator_only"
        " CHECK (permission_code NOT LIKE 'platform.%');"
    )
    op.execute("REVOKE DELETE ON app_user, tenant_membership, jobs FROM aip_app;")


def downgrade() -> None:
    raise NotImplementedError("forward-only")
