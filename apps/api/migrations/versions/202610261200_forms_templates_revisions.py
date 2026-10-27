"""forms_templates_revisions

FORMS-01 (ADR 0002): the forms module's first two tenant tables, each from
``db/templates/tenant_table.sql.tpl`` (uuid PK, tenant_id, timestamps, soft delete, FORCE RLS with
the fail-closed NULLIF policy). Deletes are soft, so ``aip_app`` loses the template's DELETE grant.

- ``form_templates`` (``sync=True``) is a template's identity: a tenant-unique ``code``, a ``kind``
  and a ``status`` (draft/active/retired), pointing at its current published revision.
- ``form_revisions`` holds the frozen JSON ``schema`` of each revision. ``(id, tenant_id)`` is
  unique on both tables so the composite FKs keep a revision and a template's current revision in
  the same tenant. Two partial unique indexes enforce one open draft and one published revision per
  template. A ``BEFORE UPDATE OR DELETE`` trigger freezes a revision once it leaves ``draft``: its
  schema, hash, evaluator version, numbering, publish stamp and soft-delete flag can never change,
  it can never be hard-deleted, and the only status move allowed is ``published -> superseded``.
  Drafts stay fully editable.

Revision ID: 202610261200
Revises: 202610251400
Create Date: 2026-10-26 12:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610261200"
down_revision: str | None = "202610251400"
branch_labels = None
depends_on = None

# The kind and status vocabularies, the code pattern and the published-hash shape are inline CHECKs
# (plain op.execute literals, not f-strings: aip-db lint allows only a literal or render_template).


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="form_templates",
            columns=(
                "code text NOT NULL, name text NOT NULL, kind text NOT NULL, "
                "status text NOT NULL, current_revision_id uuid NULL, created_by uuid NULL"
            ),
            sync=True,
        )
    )
    op.execute("""
    ALTER TABLE form_templates ALTER COLUMN status SET DEFAULT 'draft';
    ALTER TABLE form_templates
      ADD CONSTRAINT fk_form_templates_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      ADD CONSTRAINT uq_form_templates_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT ck_form_templates_kind
        CHECK (kind IN ('inspection', 'itp', 'rfi', 'permit', 'test_report')),
      ADD CONSTRAINT ck_form_templates_status
        CHECK (status IN ('draft', 'active', 'retired')),
      ADD CONSTRAINT ck_form_templates_code CHECK (code ~ '^[a-z][a-z0-9-]{1,62}$');

    CREATE UNIQUE INDEX uq_form_templates_tenant_id_code
      ON form_templates (tenant_id, code) WHERE deleted_at IS NULL;
    CREATE INDEX ix_form_templates_tenant_id_kind_status
      ON form_templates (tenant_id, kind, status);

    REVOKE DELETE ON form_templates FROM aip_app;
    """)

    op.execute(
        render_template(
            "tenant_table",
            table="form_revisions",
            columns=(
                "template_id uuid NOT NULL, revision_no integer NOT NULL, "
                "status text NOT NULL, schema jsonb NOT NULL, "
                "schema_hash text NULL, evaluator_version text NULL, change_note text NULL, "
                "published_at timestamptz NULL, published_by uuid NULL, created_by uuid NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE form_revisions ALTER COLUMN status SET DEFAULT 'draft';
    ALTER TABLE form_revisions
      ADD CONSTRAINT uq_form_revisions_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT uq_form_revisions_template_id_revision_no UNIQUE (template_id, revision_no),
      ADD CONSTRAINT ck_form_revisions_status
        CHECK (status IN ('draft', 'published', 'superseded')),
      ADD CONSTRAINT ck_form_revisions_revision_no CHECK (revision_no >= 1),
      ADD CONSTRAINT ck_form_revisions_frozen_shape
        CHECK (status = 'draft'
               OR (schema_hash ~ '^[0-9a-f]{64}$' AND published_at IS NOT NULL)),
      -- (template_id, tenant_id) keeps a revision within its own tenant's template.
      ADD CONSTRAINT fk_form_revisions_template
        FOREIGN KEY (template_id, tenant_id) REFERENCES form_templates (id, tenant_id);

    -- One open draft and one published revision per template.
    CREATE UNIQUE INDEX uq_form_revisions_one_draft
      ON form_revisions (template_id) WHERE status = 'draft' AND deleted_at IS NULL;
    CREATE UNIQUE INDEX uq_form_revisions_one_published
      ON form_revisions (template_id) WHERE status = 'published';
    CREATE INDEX ix_form_revisions_tenant_id_template_id_status
      ON form_revisions (tenant_id, template_id, status);

    REVOKE DELETE ON form_revisions FROM aip_app;

    -- The template's current revision must be a revision of that same template (same tenant).
    ALTER TABLE form_templates
      ADD CONSTRAINT fk_form_templates_current_revision
        FOREIGN KEY (current_revision_id, tenant_id) REFERENCES form_revisions (id, tenant_id);

    CREATE FUNCTION form_revisions_freeze() RETURNS trigger
      LANGUAGE plpgsql AS $fn$
      BEGIN
        IF TG_OP = 'DELETE' THEN
          IF OLD.status <> 'draft' THEN
            RAISE EXCEPTION 'form revision is frozen' USING ERRCODE = 'P0001';
          END IF;
          RETURN OLD;
        END IF;
        IF OLD.status <> 'draft' THEN
          IF NEW.schema IS DISTINCT FROM OLD.schema
             OR NEW.schema_hash IS DISTINCT FROM OLD.schema_hash
             OR NEW.evaluator_version IS DISTINCT FROM OLD.evaluator_version
             OR NEW.revision_no IS DISTINCT FROM OLD.revision_no
             OR NEW.template_id IS DISTINCT FROM OLD.template_id
             OR NEW.published_at IS DISTINCT FROM OLD.published_at
             OR NEW.published_by IS DISTINCT FROM OLD.published_by
             OR NEW.deleted_at IS DISTINCT FROM OLD.deleted_at THEN
            RAISE EXCEPTION 'form revision is frozen' USING ERRCODE = 'P0001';
          END IF;
          IF NEW.status IS DISTINCT FROM OLD.status
             AND NOT (OLD.status = 'published' AND NEW.status = 'superseded') THEN
            RAISE EXCEPTION 'form revision is frozen' USING ERRCODE = 'P0001';
          END IF;
        END IF;
        RETURN NEW;
      END;
      $fn$;

    CREATE TRIGGER form_revisions_freeze
      BEFORE UPDATE OR DELETE ON form_revisions
      FOR EACH ROW EXECUTE FUNCTION form_revisions_freeze();
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
