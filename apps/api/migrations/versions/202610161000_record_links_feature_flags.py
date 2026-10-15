"""record_links_feature_flags

ARCH-08 (ADR 0002, ADR 0008): two tenant tables from ``db/templates/tenant_table.sql.tpl`` (uuid PK,
tenant_id, timestamps, soft delete, FORCE RLS with the fail-closed NULLIF policy). Deletes are
soft, so ``aip_app`` loses the template's DELETE grant and keeps SELECT, INSERT, UPDATE.

- ``record_links``: a directed link ``(from_type, from_id) -> (to_type, to_id)`` of one
  ``link_kind``, optionally about an asset (``asset_id``; the asset table does not exist yet, so no
  foreign key). One live row per link: a partial unique index over the link's identity
  ``WHERE deleted_at IS NULL``, which ``LinkService.link`` targets with ``ON CONFLICT DO NOTHING``
  and which also serves the traversal's lookups by ``(tenant_id, from_type, from_id)``.
- ``tenant_feature_flags``: a tenant's value for one release flag (rollout or kill switch). A
  missing row means the flag's code-level default. Release flags are not entitlements (ADR 0008).

Revision ID: 202610161000
Revises: 202610152000
Create Date: 2026-10-16 10:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610161000"
down_revision: str | None = "202610152000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="record_links",
            columns=(
                "from_type text NOT NULL, from_id uuid NOT NULL, "
                "to_type text NOT NULL, to_id uuid NOT NULL, "
                "asset_id uuid NULL, link_kind text NOT NULL, created_by uuid NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE record_links
      ADD CONSTRAINT fk_record_links_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      ADD CONSTRAINT ck_record_links_from_type CHECK (from_type ~ '^[a-z][a-z0-9_]{0,62}$'),
      ADD CONSTRAINT ck_record_links_to_type CHECK (to_type ~ '^[a-z][a-z0-9_]{0,62}$'),
      ADD CONSTRAINT ck_record_links_link_kind CHECK (link_kind ~ '^[a-z][a-z0-9_]{0,62}$'),
      ADD CONSTRAINT ck_record_links_not_self
        CHECK (from_type <> to_type OR from_id <> to_id);

    CREATE UNIQUE INDEX ux_record_links_live
      ON record_links (tenant_id, from_type, from_id, to_type, to_id, link_kind)
      WHERE deleted_at IS NULL;
    CREATE INDEX ix_record_links_to
      ON record_links (tenant_id, to_type, to_id) WHERE deleted_at IS NULL;

    REVOKE DELETE ON record_links FROM aip_app;
    """)

    op.execute(
        render_template(
            "tenant_table",
            table="tenant_feature_flags",
            columns="flag text NOT NULL, enabled boolean NOT NULL, updated_by uuid NULL",
        )
    )
    op.execute("""
    ALTER TABLE tenant_feature_flags
      ADD CONSTRAINT fk_tenant_feature_flags_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      ADD CONSTRAINT ck_tenant_feature_flags_flag CHECK (flag ~ '^[a-z][a-z0-9_]{0,62}$');

    CREATE UNIQUE INDEX ux_tenant_feature_flags_live
      ON tenant_feature_flags (tenant_id, flag) WHERE deleted_at IS NULL;

    REVOKE DELETE ON tenant_feature_flags FROM aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
