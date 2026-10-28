"""report_engine_templates

REPORTS-01 (ADR 0002): the report_engine module's first tenant table, from
``db/templates/tenant_table.sql.tpl`` (uuid PK, tenant_id, timestamps, soft delete, FORCE RLS with
the fail-closed NULLIF policy). Deletes are soft, so ``aip_app`` loses the template's DELETE grant.

``report_templates`` holds one row per template version: ``(tenant_id, key, variant, version)`` is
unique, so a key carries its internal, client and certificate variants side by side. The row holds
the whole package (definition with its sample data, Jinja body, stylesheet and base64 assets) and
its ``content_sha256``. A ``BEFORE UPDATE`` trigger freezes a row once it leaves ``draft``: only
``status`` (``published -> retired``) and ``updated_at`` may change, and only a draft may be
soft-deleted. A retired row is kept, so a pinned report can always be re-rendered.

Revision ID: 202610281500
Revises: 202610281300
Create Date: 2026-10-28 15:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610281500"
down_revision: str | None = "202610281300"
branch_labels = None
depends_on = None

# The vocabularies, the hash shape and the publish stamp are inline CHECKs (plain op.execute
# literals, not f-strings: aip-db lint allows only a literal or render_template).


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="report_templates",
            columns=(
                "key text NOT NULL, version integer NOT NULL, variant text NOT NULL, "
                "record_type text NOT NULL, name_key text NOT NULL, orientation text NOT NULL, "
                "paper text NOT NULL, definition jsonb NOT NULL, body text NOT NULL, "
                "css text NOT NULL, assets jsonb NOT NULL, content_sha256 text NOT NULL, "
                "status text NOT NULL, source text NOT NULL, client_company_id uuid NULL, "
                "published_at timestamptz NULL, published_by uuid NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE report_templates ALTER COLUMN status SET DEFAULT 'draft';
    ALTER TABLE report_templates
      ADD CONSTRAINT fk_report_templates_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      ADD CONSTRAINT uq_report_templates_tenant_id_key_variant_version
        UNIQUE (tenant_id, key, variant, version),
      ADD CONSTRAINT ck_report_templates_version CHECK (version >= 1),
      ADD CONSTRAINT ck_report_templates_variant
        CHECK (variant IN ('internal', 'client', 'certificate')),
      ADD CONSTRAINT ck_report_templates_orientation
        CHECK (orientation IN ('portrait', 'landscape')),
      ADD CONSTRAINT ck_report_templates_paper CHECK (paper IN ('A4', 'A3')),
      ADD CONSTRAINT ck_report_templates_status
        CHECK (status IN ('draft', 'published', 'retired')),
      ADD CONSTRAINT ck_report_templates_source CHECK (source IN ('config', 'upload')),
      ADD CONSTRAINT ck_report_templates_content_sha256
        CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
      ADD CONSTRAINT ck_report_templates_published_at
        CHECK (status <> 'published' OR published_at IS NOT NULL);

    CREATE INDEX ix_report_templates_tenant_id_record_type_variant_status
      ON report_templates (tenant_id, record_type, variant, status);

    REVOKE DELETE ON report_templates FROM aip_app;

    CREATE FUNCTION report_templates_published_immutable() RETURNS trigger
      LANGUAGE plpgsql AS $fn$
      BEGIN
        IF OLD.status <> 'draft' THEN
          IF NEW.id IS DISTINCT FROM OLD.id
             OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
             OR NEW.key IS DISTINCT FROM OLD.key
             OR NEW.version IS DISTINCT FROM OLD.version
             OR NEW.variant IS DISTINCT FROM OLD.variant
             OR NEW.record_type IS DISTINCT FROM OLD.record_type
             OR NEW.name_key IS DISTINCT FROM OLD.name_key
             OR NEW.orientation IS DISTINCT FROM OLD.orientation
             OR NEW.paper IS DISTINCT FROM OLD.paper
             OR NEW.definition IS DISTINCT FROM OLD.definition
             OR NEW.body IS DISTINCT FROM OLD.body
             OR NEW.css IS DISTINCT FROM OLD.css
             OR NEW.assets IS DISTINCT FROM OLD.assets
             OR NEW.content_sha256 IS DISTINCT FROM OLD.content_sha256
             OR NEW.source IS DISTINCT FROM OLD.source
             OR NEW.client_company_id IS DISTINCT FROM OLD.client_company_id
             OR NEW.published_at IS DISTINCT FROM OLD.published_at
             OR NEW.published_by IS DISTINCT FROM OLD.published_by
             OR NEW.created_at IS DISTINCT FROM OLD.created_at
             OR NEW.deleted_at IS DISTINCT FROM OLD.deleted_at
             OR (NEW.status IS DISTINCT FROM OLD.status
                 AND NOT (OLD.status = 'published' AND NEW.status = 'retired')) THEN
            RAISE EXCEPTION 'report template is published' USING ERRCODE = '23514';
          END IF;
        END IF;
        RETURN NEW;
      END;
      $fn$;

    CREATE TRIGGER report_templates_published_immutable
      BEFORE UPDATE ON report_templates
      FOR EACH ROW EXECUTE FUNCTION report_templates_published_immutable();
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
