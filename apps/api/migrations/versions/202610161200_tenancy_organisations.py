"""tenancy_organisations

TENANCY-03: ``organisations``, the owner, client and subcontractor parties inside a tenant (Rio
Tinto is a client organisation in Kaefer's tenant), from ``db/templates/tenant_table.sql.tpl``
(uuid PK, tenant_id, timestamps, soft delete, FORCE RLS with the fail-closed NULLIF policy).

Names are unique per tenant ignoring case among live rows. ``(id, tenant_id)`` is unique so later
tables (``org_asset_shares``, memberships) can reference an organisation together with its tenant.
Deletes are soft, so ``aip_app`` loses the template's DELETE grant.

No rows are written here: FORCE RLS hides ``tenants`` from the migration role, so the owner
organisation of each fixture tenant comes from the tenancy seed, and of a real tenant from
provisioning (TENANCY-05).

Revision ID: 202610161200
Revises: 202610161000
Create Date: 2026-10-16 12:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610161200"
down_revision: str | None = "202610161000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="organisations",
            columns=(
                "name text NOT NULL, org_type text NOT NULL, registration_number text NULL, "
                "status text NOT NULL, sync_version integer NOT NULL DEFAULT 1"
            ),
        )
    )
    op.execute("""
    ALTER TABLE organisations ALTER COLUMN status SET DEFAULT 'active';
    ALTER TABLE organisations
      ADD CONSTRAINT uq_organisations_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT ck_organisations_name CHECK (btrim(name) <> ''),
      ADD CONSTRAINT ck_organisations_org_type
        CHECK (org_type IN ('owner', 'client', 'subcontractor')),
      ADD CONSTRAINT ck_organisations_status CHECK (status IN ('active', 'inactive')),
      ADD CONSTRAINT ck_organisations_sync_version CHECK (sync_version >= 1);

    CREATE UNIQUE INDEX uq_organisations_tenant_id_lower_name
      ON organisations (tenant_id, lower(name)) WHERE deleted_at IS NULL;
    CREATE INDEX ix_organisations_tenant_id_org_type ON organisations (tenant_id, org_type);

    REVOKE DELETE ON organisations FROM aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
