"""item_types_core

ITEMTYPES-01: the configuration layer's three tenant tables, each from
``db/templates/tenant_table.sql.tpl`` (uuid PK, tenant_id, timestamps, soft delete, FORCE RLS with
the fail-closed NULLIF policy). Deletes are soft, so ``aip_app`` loses the template's DELETE grant.

``content_types`` are the top-level kinds (Asset, Staff, ...); ``item_categories`` sit beneath a
content type; ``item_types`` sit beneath a category. Keys are stable snake_case identifiers unique
per tenant among live rows; names are tenant labels. ``(id, tenant_id)`` is unique on every table
so a child references its parent by ``(parent, tenant_id)`` and can never point at another tenant's
row, and so ITEMTYPES-02/ASSETS-02 can reference ``(item_type_id, tenant_id)``.

Revision ID: 202610251200
Revises: 202610242000
Create Date: 2026-10-25 12:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610251200"
down_revision: str | None = "202610242000"
branch_labels = None
depends_on = None

# Keys are a stable snake_case identifier of 1-63 chars; an icon is an @aip/ui icon name (the web
# falls back to folder for an unknown one). The checks are inline below, not f-strings: aip-db lint
# allows only a plain op.execute(raw SQL) literal or render_template(...).


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="content_types",
            columns=(
                "key text NOT NULL, name text NOT NULL, icon text NOT NULL, "
                "sort_order integer NOT NULL DEFAULT 0, "
                "show_in_nav boolean NOT NULL DEFAULT true, "
                "is_system boolean NOT NULL DEFAULT false, "
                "sync_version integer NOT NULL DEFAULT 1"
            ),
        )
    )
    op.execute("""
    ALTER TABLE content_types ALTER COLUMN icon SET DEFAULT 'folder';
    ALTER TABLE content_types
      ADD CONSTRAINT uq_content_types_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT ck_content_types_key CHECK (key ~ '^[a-z][a-z0-9_]{0,62}$'),
      ADD CONSTRAINT ck_content_types_name CHECK (name <> ''),
      ADD CONSTRAINT ck_content_types_icon CHECK (icon ~ '^[a-z][a-z0-9-]{0,39}$'),
      ADD CONSTRAINT ck_content_types_sync_version CHECK (sync_version >= 1);

    CREATE UNIQUE INDEX uq_content_types_tenant_id_key
      ON content_types (tenant_id, key) WHERE deleted_at IS NULL;

    REVOKE DELETE ON content_types FROM aip_app;
    """)

    op.execute(
        render_template(
            "tenant_table",
            table="item_categories",
            columns=(
                "content_type_id uuid NOT NULL, key text NOT NULL, name text NOT NULL, "
                "applicable_for text NOT NULL, sort_order integer NOT NULL DEFAULT 0, "
                "sync_version integer NOT NULL DEFAULT 1"
            ),
        )
    )
    op.execute("""
    ALTER TABLE item_categories ALTER COLUMN applicable_for SET DEFAULT 'any';
    ALTER TABLE item_categories
      ADD CONSTRAINT uq_item_categories_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT ck_item_categories_key CHECK (key ~ '^[a-z][a-z0-9_]{0,62}$'),
      ADD CONSTRAINT ck_item_categories_name CHECK (name <> ''),
      ADD CONSTRAINT ck_item_categories_applicable_for
        CHECK (applicable_for IN ('any', 'item', 'module')),
      ADD CONSTRAINT ck_item_categories_sync_version CHECK (sync_version >= 1),
      -- (content_type_id, tenant_id) keeps a category within its own tenant's content type.
      ADD CONSTRAINT fk_item_categories_content_type
        FOREIGN KEY (content_type_id, tenant_id) REFERENCES content_types (id, tenant_id);

    CREATE UNIQUE INDEX uq_item_categories_tenant_id_content_type_id_key
      ON item_categories (tenant_id, content_type_id, key) WHERE deleted_at IS NULL;
    CREATE INDEX ix_item_categories_tenant_id_content_type_id_sort_order
      ON item_categories (tenant_id, content_type_id, sort_order);

    REVOKE DELETE ON item_categories FROM aip_app;
    """)

    op.execute(
        render_template(
            "tenant_table",
            table="item_types",
            columns=(
                "category_id uuid NOT NULL, key text NOT NULL, name text NOT NULL, "
                "description text NULL, is_component boolean NOT NULL DEFAULT false, "
                "allows_components boolean NOT NULL DEFAULT false, "
                "sync_version integer NOT NULL DEFAULT 1"
            ),
        )
    )
    op.execute("""
    ALTER TABLE item_types
      ADD CONSTRAINT uq_item_types_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT ck_item_types_key CHECK (key ~ '^[a-z][a-z0-9_]{0,62}$'),
      ADD CONSTRAINT ck_item_types_name CHECK (name <> ''),
      ADD CONSTRAINT ck_item_types_sync_version CHECK (sync_version >= 1),
      -- (category_id, tenant_id) so an item type can never point at another tenant's category.
      ADD CONSTRAINT fk_item_types_category
        FOREIGN KEY (category_id, tenant_id) REFERENCES item_categories (id, tenant_id);

    CREATE UNIQUE INDEX uq_item_types_tenant_id_key
      ON item_types (tenant_id, key) WHERE deleted_at IS NULL;
    CREATE INDEX ix_item_types_tenant_id_category_id
      ON item_types (tenant_id, category_id);

    REVOKE DELETE ON item_types FROM aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
