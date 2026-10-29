"""assets_item_types

ASSETS-02 (ADR 0036): typed assets. ``assets`` gains the item type an asset is typed with, the
published item-type version it is pinned to, and its JSONB ``attributes`` (validated in the app
against the pinned version's compiled schema through ``ItemTypesApi``, ADR 0002).

- ``ck_assets_item_type_pinned``: a typed asset always carries both ids, an untyped one neither.
- ``ck_assets_attributes_object``: attributes are a JSON object.
- ``ck_assets_untyped_attributes``: an untyped asset has ``{}`` attributes.
- Both foreign keys are composite with ``tenant_id`` (ITEMTYPES-01/02 made ``(id, tenant_id)``
  unique), so an asset can never point at another tenant's item type or version.

Revision ID: 202610281600
Revises: 202610281500
Create Date: 2026-10-28 16:00:00+00:00
"""

from alembic import op

revision: str = "202610281600"
down_revision: str | None = "202610281500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE assets
      ADD COLUMN item_type_id uuid NULL,
      ADD COLUMN item_type_version_id uuid NULL,
      ADD COLUMN attributes jsonb NOT NULL DEFAULT '{}'::jsonb;

    ALTER TABLE assets
      ADD CONSTRAINT ck_assets_item_type_pinned
        CHECK ((item_type_id IS NULL) = (item_type_version_id IS NULL)),
      ADD CONSTRAINT ck_assets_attributes_object CHECK (jsonb_typeof(attributes) = 'object'),
      ADD CONSTRAINT ck_assets_untyped_attributes
        CHECK (item_type_id IS NOT NULL OR attributes = '{}'::jsonb),
      -- (…, tenant_id) so an asset can never point at another tenant's item type or version.
      ADD CONSTRAINT fk_assets_item_type
        FOREIGN KEY (item_type_id, tenant_id) REFERENCES item_types (id, tenant_id),
      ADD CONSTRAINT fk_assets_item_type_version
        FOREIGN KEY (item_type_version_id, tenant_id)
        REFERENCES item_type_versions (id, tenant_id);

    CREATE INDEX ix_assets_tenant_id_item_type_id ON assets (tenant_id, item_type_id);
    CREATE INDEX ix_assets_attributes ON assets USING gin (attributes jsonb_path_ops);
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
