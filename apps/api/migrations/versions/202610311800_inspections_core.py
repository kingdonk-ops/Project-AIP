"""inspections_core

INSPECTIONS-01 (ADR 0002, ADR 0036): the inspections module's first table, from
``db/templates/tenant_table.sql.tpl`` with the offline-sync columns (uuid PK, tenant_id,
timestamps, soft delete, ``client_generated_id``/``sync_version``, FORCE RLS with the fail-closed
NULLIF policy), plus the ACCESS-03 project-scope policy because it carries ``project_id``.

- An inspection runs against one asset from one form revision, ``template_revision_id``, pinned at
  creation and never changed. ``kind`` and ``source`` are inline CHECKs; ``source_ref_id`` (the
  scope task, or the inspection being re-inspected) is required for ``scope_task`` and
  ``reinspection``.
- ``workflow_instance_id`` is the record's approvals instance (unique per tenant); ``state`` is a
  cache of its ``current_state`` for registers, the instance is the truth.
- ``(id, tenant_id)`` is unique so later inspections tables reference an inspection in their own
  tenant. No foreign keys to other modules' tables (assets, forms, projects, approvals): the
  service checks existence through their ``api.py``. Deletes are soft, so ``aip_app`` loses DELETE.

Revision ID: 202610311800
Revises: 202610311700
Create Date: 2026-10-31 18:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610311800"
down_revision: str | None = "202610311700"
branch_labels = None
depends_on = None

# The kind and source vocabularies are inline CHECKs (plain op.execute literals, not f-strings:
# aip-db lint allows only a literal or render_template).


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="inspections",
            columns=(
                "asset_id uuid NOT NULL, project_id uuid NULL, template_id uuid NOT NULL, "
                "template_revision_id uuid NOT NULL, kind text NOT NULL, source text NOT NULL, "
                "source_ref_id uuid NULL, itp_parent_id uuid NULL, "
                "workflow_instance_id uuid NOT NULL, state text NOT NULL, created_by uuid NOT NULL"
            ),
            sync=True,
        )
    )
    op.execute("""
    ALTER TABLE inspections
      ADD CONSTRAINT fk_inspections_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      ADD CONSTRAINT uq_inspections_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT ck_inspections_kind CHECK (kind IN ('inspection', 'itp', 'rfi')),
      ADD CONSTRAINT ck_inspections_source
        CHECK (source IN ('manual', 'scope_task', 'reinspection', 'import')),
      ADD CONSTRAINT ck_inspections_source_ref
        CHECK (source NOT IN ('scope_task', 'reinspection') OR source_ref_id IS NOT NULL);

    CREATE INDEX ix_inspections_tenant_id_asset_id ON inspections (tenant_id, asset_id);
    CREATE INDEX ix_inspections_tenant_id_project_id_state
      ON inspections (tenant_id, project_id, state);
    CREATE INDEX ix_inspections_tenant_id_template_revision_id
      ON inspections (tenant_id, template_revision_id);
    CREATE UNIQUE INDEX uq_inspections_tenant_id_workflow_instance_id
      ON inspections (tenant_id, workflow_instance_id);

    REVOKE DELETE ON inspections FROM aip_app;

    -- The pinned form revision, the asset and the workflow instance never change once created.
    CREATE FUNCTION inspections_pinned_immutable() RETURNS trigger
      LANGUAGE plpgsql AS $fn$
      BEGIN
        IF NEW.template_revision_id IS DISTINCT FROM OLD.template_revision_id
           OR NEW.template_id IS DISTINCT FROM OLD.template_id
           OR NEW.asset_id IS DISTINCT FROM OLD.asset_id
           OR NEW.workflow_instance_id IS DISTINCT FROM OLD.workflow_instance_id THEN
          RAISE EXCEPTION 'inspection pin is immutable' USING ERRCODE = 'P0001';
        END IF;
        RETURN NEW;
      END;
      $fn$;

    CREATE TRIGGER inspections_pinned_immutable
      BEFORE UPDATE ON inspections
      FOR EACH ROW EXECUTE FUNCTION inspections_pinned_immutable();
    """)
    op.execute(render_template("project_scoped_policy", table="inspections"))


def downgrade() -> None:
    raise NotImplementedError("forward-only")
