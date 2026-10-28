"""item_types_versions

ITEMTYPES-02 (ADR 0036 choice 2): immutable, numbered attribute-schema versions per item type, from
``db/templates/tenant_table.sql.tpl`` (uuid PK, tenant_id, timestamps, soft delete, FORCE RLS with
the fail-closed NULLIF policy). Deletes are soft, so ``aip_app`` loses the template's DELETE grant.

- ``item_type_versions`` holds each version's ``attributes`` (the definitions, in display order)
  and, once published, the ``compiled_schema`` asset attributes are validated against. Version
  numbers are unique per item type among live rows and at most one live draft exists per item type
  (two partial unique indexes). A ``BEFORE UPDATE`` trigger refuses any change to a published row
  (SQLSTATE 55000), so a version an asset pinned can never change under it. Drafts stay editable
  and soft-deletable.
- ``item_types.published_version_id`` points at the current published version; ``(id,
  tenant_id)`` is unique on the versions table so the composite FKs keep both in one tenant.

Revision ID: 202610281300
Revises: 202610281200
Create Date: 2026-10-28 13:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610281300"
down_revision: str | None = "202610281200"
branch_labels = None
depends_on = None

# The status vocabulary and the published-shape rule are inline CHECKs (plain op.execute literals,
# not f-strings: aip-db lint allows only a literal or render_template).


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="item_type_versions",
            columns=(
                "item_type_id uuid NOT NULL, version integer NOT NULL, "
                "status text NOT NULL, attributes jsonb NOT NULL, compiled_schema jsonb NULL, "
                "change_summary text NULL, published_at timestamptz NULL, "
                "published_by uuid NULL, created_by uuid NULL, "
                "sync_version integer NOT NULL DEFAULT 1"
            ),
        )
    )
    op.execute("""
    ALTER TABLE item_type_versions ALTER COLUMN status SET DEFAULT 'draft';
    ALTER TABLE item_type_versions ALTER COLUMN attributes SET DEFAULT '[]';
    ALTER TABLE item_type_versions
      ADD CONSTRAINT uq_item_type_versions_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT ck_item_type_versions_status CHECK (status IN ('draft', 'published')),
      ADD CONSTRAINT ck_item_type_versions_version CHECK (version >= 1),
      ADD CONSTRAINT ck_item_type_versions_attributes CHECK (jsonb_typeof(attributes) = 'array'),
      ADD CONSTRAINT ck_item_type_versions_published_shape
        CHECK ((status = 'published') = (compiled_schema IS NOT NULL AND published_at IS NOT NULL)),
      ADD CONSTRAINT ck_item_type_versions_sync_version CHECK (sync_version >= 1),
      -- (item_type_id, tenant_id) keeps a version within its own tenant's item type.
      ADD CONSTRAINT fk_item_type_versions_item_type
        FOREIGN KEY (item_type_id, tenant_id) REFERENCES item_types (id, tenant_id);

    CREATE UNIQUE INDEX uq_item_type_versions_tenant_id_item_type_id_version
      ON item_type_versions (tenant_id, item_type_id, version) WHERE deleted_at IS NULL;
    -- At most one open draft per item type.
    CREATE UNIQUE INDEX uq_item_type_versions_one_draft
      ON item_type_versions (tenant_id, item_type_id)
      WHERE status = 'draft' AND deleted_at IS NULL;

    REVOKE DELETE ON item_type_versions FROM aip_app;

    CREATE FUNCTION item_type_versions_freeze() RETURNS trigger
      LANGUAGE plpgsql AS $fn$
      BEGIN
        IF OLD.status = 'published' THEN
          RAISE EXCEPTION 'published item type version is immutable' USING ERRCODE = '55000';
        END IF;
        RETURN NEW;
      END;
      $fn$;

    CREATE TRIGGER item_type_versions_freeze
      BEFORE UPDATE ON item_type_versions
      FOR EACH ROW EXECUTE FUNCTION item_type_versions_freeze();

    -- The item type's current published version must be in the same tenant.
    ALTER TABLE item_types ADD COLUMN published_version_id uuid NULL;
    ALTER TABLE item_types
      ADD CONSTRAINT fk_item_types_published_version
        FOREIGN KEY (published_version_id, tenant_id)
        REFERENCES item_type_versions (id, tenant_id);
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
