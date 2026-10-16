"""approvals_workflows

APPROVALS-01 (ADR 0002): versioned workflow definitions, instances pinned to a version, and the
append-only definition audit (``docs/blueprint/modules/approvals/data-model.md``).

- ``workflow_definitions`` (``tenant_table``): one row per version of a definition ``key``, tenant
  wide (``project_id`` NULL) or for one project. ``states``/``transitions``/``initial_state`` hold
  the validated spec. ``unique (tenant_id, key, version)``, and a partial unique index allows at
  most one ``active`` version per key and scope (NULL project folded to the zero uuid).
  ``uq_workflow_definitions_id_tenant_id`` lets instances and audit rows reference a definition in
  their own tenant only.
- ``workflow_instances`` (``tenant_table`` with ``sync=True``): one live instance per record,
  pinned to the definition version it started under. Route and step columns arrive with
  APPROVALS-02/04 (their tables do not exist yet).
- ``workflow_definition_audit`` (``append_only_table``, monthly partitions on ``created_at``,
  registered in ``partition_settings``): the ``{before, after}`` of each publish. ``aip_app`` has
  only SELECT and INSERT.

``project_id`` and ``record_id`` are plain uuids: the projects table and record tables belong to
other modules. Deletes are soft on the two mutable tables, so ``aip_app`` loses DELETE.

Revision ID: 202610161400
Revises: 202610161600
Create Date: 2026-10-16 14:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610161400"
down_revision: str | None = "202610161600"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="workflow_definitions",
            columns=(
                "record_type text NOT NULL, project_id uuid NULL, key text NOT NULL, "
                "version integer NOT NULL, status text NOT NULL, "
                "states jsonb NOT NULL, transitions jsonb NOT NULL, initial_state text NOT NULL, "
                "is_preset boolean NOT NULL DEFAULT false, created_by uuid NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE workflow_definitions
      ALTER COLUMN status SET DEFAULT 'draft';
    ALTER TABLE workflow_definitions
      ADD CONSTRAINT fk_workflow_definitions_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      ADD CONSTRAINT uq_workflow_definitions_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT uq_workflow_definitions_key_version UNIQUE (tenant_id, key, version),
      ADD CONSTRAINT ck_workflow_definitions_status
        CHECK (status IN ('draft', 'active', 'retired')),
      ADD CONSTRAINT ck_workflow_definitions_key CHECK (key ~ '^[a-z][a-z0-9_]{0,62}$'),
      ADD CONSTRAINT ck_workflow_definitions_record_type
        CHECK (record_type ~ '^[a-z][a-z0-9_]{0,62}$'),
      ADD CONSTRAINT ck_workflow_definitions_version CHECK (version >= 1),
      ADD CONSTRAINT ck_workflow_definitions_states CHECK (jsonb_typeof(states) = 'array'),
      ADD CONSTRAINT ck_workflow_definitions_transitions
        CHECK (jsonb_typeof(transitions) = 'array');

    CREATE UNIQUE INDEX ux_workflow_definitions_active
      ON workflow_definitions
        (tenant_id, key, coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid))
      WHERE status = 'active';
    CREATE INDEX ix_workflow_definitions_resolve
      ON workflow_definitions (tenant_id, record_type, project_id, status)
      WHERE deleted_at IS NULL;

    REVOKE DELETE ON workflow_definitions FROM aip_app;
    """)

    op.execute(
        render_template(
            "tenant_table",
            table="workflow_instances",
            columns=(
                "project_id uuid NULL, definition_id uuid NOT NULL, record_type text NOT NULL, "
                "record_id uuid NOT NULL, asset_id uuid NULL, current_state text NOT NULL, "
                "record_value numeric(18, 2) NULL, currency char(3) NULL, "
                "visibility_scope text NULL, created_by uuid NULL"
            ),
            sync=True,
        )
    )
    op.execute("""
    ALTER TABLE workflow_instances
      ADD CONSTRAINT fk_workflow_instances_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      ADD CONSTRAINT fk_workflow_instances_definition
        FOREIGN KEY (definition_id, tenant_id)
        REFERENCES workflow_definitions (id, tenant_id),
      ADD CONSTRAINT ck_workflow_instances_record_type
        CHECK (record_type ~ '^[a-z][a-z0-9_]{0,62}$'),
      ADD CONSTRAINT ck_workflow_instances_current_state
        CHECK (current_state ~ '^[a-z][a-z0-9_]{0,62}$');

    CREATE UNIQUE INDEX ux_workflow_instances_record
      ON workflow_instances (tenant_id, record_type, record_id) WHERE deleted_at IS NULL;
    CREATE INDEX ix_workflow_instances_definition_id
      ON workflow_instances (tenant_id, definition_id);

    REVOKE DELETE ON workflow_instances FROM aip_app;
    """)

    op.execute(
        render_template(
            "append_only_table",
            table="workflow_definition_audit",
            columns="definition_id uuid NOT NULL, actor_id uuid NULL, change jsonb NOT NULL",
            partition_column="created_at",
        )
    )
    op.execute("""
    ALTER TABLE workflow_definition_audit
      ADD CONSTRAINT fk_workflow_definition_audit_definition
        FOREIGN KEY (definition_id, tenant_id)
        REFERENCES workflow_definitions (id, tenant_id),
      ADD CONSTRAINT ck_workflow_definition_audit_change CHECK (jsonb_typeof(change) = 'object');

    CREATE INDEX ix_workflow_definition_audit_definition_id
      ON workflow_definition_audit (tenant_id, definition_id, created_at);

    -- The template already revokes these; restated so the append-only rule reads in one place.
    REVOKE UPDATE, DELETE, TRUNCATE ON workflow_definition_audit FROM aip_app, aip_jobs;

    INSERT INTO partition_settings (table_name) VALUES ('workflow_definition_audit');
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
