"""assets_tree

ASSETS-01: the tenant-owned asset tree on ltree. One table, ``assets``, from
``db/templates/tenant_table.sql.tpl`` with ``sync=True`` (uuid PK, tenant_id, timestamps, soft
delete, ``client_generated_id`` + ``sync_version`` and their unique index, FORCE RLS with the
fail-closed NULLIF policy). Deletes are soft, so ``aip_app`` loses the template's DELETE grant.

Each row's ltree ``path`` ends in the row's own id (its 32 hex digits), enforced by
``ck_assets_path_leaf``; a root row has a one-label path and no parent (``ck_assets_root``); the
tree is at most 15 deep (``ck_assets_depth``). ``internal_tag`` is immutable after insert (a BEFORE
UPDATE trigger), Tag Numbers are unique among live rows per tenant ignoring case, and
``(id, tenant_id)`` is unique so later modules can reference ``(asset_id, tenant_id)`` and never
point at another tenant's asset.

Revision ID: 202610242000
Revises: 202610241200
Create Date: 2026-10-24 20:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610242000"
down_revision: str | None = "202610241200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="assets",
            sync=True,
            columns=(
                "parent_id uuid NULL, path ltree NOT NULL, internal_tag text NOT NULL, "
                "tag_number text NULL, name text NOT NULL, "
                "sort_order integer NOT NULL DEFAULT 0, created_by uuid NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE assets
      ADD CONSTRAINT uq_assets_id_tenant_id UNIQUE (id, tenant_id),
      -- (parent_id, tenant_id) so a child can never point at another tenant's asset.
      ADD CONSTRAINT fk_assets_parent
        FOREIGN KEY (parent_id, tenant_id) REFERENCES assets (id, tenant_id),
      ADD CONSTRAINT ck_assets_name
        CHECK (btrim(name) <> '' AND length(name) <= 200),
      ADD CONSTRAINT ck_assets_tag_number
        CHECK (tag_number IS NULL
               OR (btrim(tag_number) = tag_number
                   AND tag_number <> '' AND length(tag_number) <= 64)),
      -- the last path label is the node's own id, so path is derivable and cannot drift from id.
      ADD CONSTRAINT ck_assets_path_leaf
        CHECK (ltree2text(subpath(path, nlevel(path) - 1)) = replace(id::text, '-', '')),
      -- a root row (no parent) is exactly a one-label path.
      ADD CONSTRAINT ck_assets_root CHECK ((parent_id IS NULL) = (nlevel(path) = 1)),
      ADD CONSTRAINT ck_assets_depth CHECK (nlevel(path) <= 15);

    CREATE INDEX ix_assets_path_gist ON assets USING gist (path);
    CREATE UNIQUE INDEX uq_assets_tenant_id_path ON assets (tenant_id, path);
    CREATE UNIQUE INDEX uq_assets_tenant_id_internal_tag ON assets (tenant_id, internal_tag);
    CREATE UNIQUE INDEX uq_assets_tenant_id_upper_tag_number
      ON assets (tenant_id, upper(tag_number))
      WHERE deleted_at IS NULL AND tag_number IS NOT NULL;
    CREATE INDEX ix_assets_tenant_id_parent_id_sort_order
      ON assets (tenant_id, parent_id, sort_order);
    CREATE INDEX ix_assets_name_trgm ON assets USING gin (name gin_trgm_ops);

    CREATE FUNCTION assets_internal_tag_immutable() RETURNS trigger
      LANGUAGE plpgsql AS $fn$
      BEGIN
        IF NEW.internal_tag IS DISTINCT FROM OLD.internal_tag THEN
          RAISE EXCEPTION 'internal_tag is immutable';
        END IF;
        RETURN NEW;
      END;
      $fn$;

    CREATE TRIGGER assets_internal_tag_immutable
      BEFORE UPDATE ON assets
      FOR EACH ROW EXECUTE FUNCTION assets_internal_tag_immutable();

    REVOKE DELETE ON assets FROM aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
