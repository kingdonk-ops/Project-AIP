"""approvals_routes

APPROVALS-04 (ADR 0002, ADR 0040): approval routes, ordered user, role or team approver steps run
serially or in parallel groups (``docs/blueprint/modules/approvals/data-model.md``).

- ``approval_route_templates`` from the tenant-table template (FORCE RLS, fail-closed policy, soft
  delete): ``on_approved_action``/``on_rejected_action`` name the workflow transitions a finished
  route takes, ``allow_self_approval`` lifts the separation-of-duties rule. ``conditions``,
  ``threshold_bands`` and ``escalation_hours`` are created but unused (R1/P1 stubs).
- ``approval_steps`` from the same template: a template step has no ``instance_id`` and no status;
  a materialised step names its instance and ``route_round`` and is ``waiting``, ``pending``,
  ``approved``, ``rejected`` or ``skipped``. ``approver_ref`` is a user, role or team id (no
  foreign key: it is polymorphic). ``required_discipline_id`` (qualification guard) is unused.
  The inbox index is ``(tenant_id, approver_type, approver_ref, status)``.
- ``workflow_instances`` gains ``route_template_id``, ``current_step_id`` (NULL unless a route
  runs), ``route_round`` (0 until the first route) and ``route_submitted_by`` (the
  separation-of-duties subject).

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


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="approval_route_templates",
            columns=(
                "name text NOT NULL, record_type text NOT NULL, "
                "conditions jsonb NOT NULL, threshold_bands jsonb NULL, "
                "escalation_hours integer NULL, version integer NOT NULL DEFAULT 1, "
                "on_approved_action text NOT NULL, on_rejected_action text NOT NULL, "
                "allow_self_approval boolean NOT NULL DEFAULT false, created_by uuid NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE approval_route_templates ALTER COLUMN conditions SET DEFAULT '{}'::jsonb;
    ALTER TABLE approval_route_templates
      ADD CONSTRAINT uq_approval_route_templates_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT fk_approval_route_templates_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      ADD CONSTRAINT ck_approval_route_templates_name
        CHECK (length(btrim(name)) BETWEEN 1 AND 120),
      ADD CONSTRAINT ck_approval_route_templates_version CHECK (version >= 1),
      ADD CONSTRAINT ck_approval_route_templates_escalation_hours
        CHECK (escalation_hours IS NULL OR escalation_hours >= 1),
      ADD CONSTRAINT ck_approval_route_templates_conditions
        CHECK (jsonb_typeof(conditions) = 'object');

    CREATE INDEX ix_approval_route_templates_tenant_id_record_type
      ON approval_route_templates (tenant_id, record_type);

    REVOKE DELETE ON approval_route_templates FROM aip_app;
    """)

    op.execute(
        render_template(
            "tenant_table",
            table="approval_steps",
            columns=(
                "route_template_id uuid NOT NULL, instance_id uuid NULL, route_round integer NULL, "
                "step_order integer NOT NULL, mode text NOT NULL, approver_type text NOT NULL, "
                "approver_ref uuid NOT NULL, required_discipline_id uuid NULL, "
                "due_hours integer NULL, due_at timestamptz NULL, status text NULL, "
                "decided_by uuid NULL, decided_at timestamptz NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE approval_steps
      ADD CONSTRAINT fk_approval_steps_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      ADD CONSTRAINT fk_approval_steps_route_template
        FOREIGN KEY (route_template_id, tenant_id)
        REFERENCES approval_route_templates (id, tenant_id),
      ADD CONSTRAINT fk_approval_steps_instance
        FOREIGN KEY (instance_id, tenant_id) REFERENCES workflow_instances (id, tenant_id),
      ADD CONSTRAINT ck_approval_steps_step_order CHECK (step_order >= 1),
      ADD CONSTRAINT ck_approval_steps_mode CHECK (mode IN ('serial', 'parallel')),
      ADD CONSTRAINT ck_approval_steps_approver_type
        CHECK (approver_type IN ('user', 'role', 'team')),
      ADD CONSTRAINT ck_approval_steps_due_hours
        CHECK (due_hours IS NULL OR due_hours BETWEEN 1 AND 8760),
      ADD CONSTRAINT ck_approval_steps_kind CHECK (
        (instance_id IS NULL AND route_round IS NULL AND status IS NULL AND due_at IS NULL
            AND decided_by IS NULL AND decided_at IS NULL)
        OR (instance_id IS NOT NULL AND route_round >= 1
            AND status IN ('waiting', 'pending', 'approved', 'rejected', 'skipped'))
      );

    CREATE INDEX ix_approval_steps_tenant_id_instance_id_step_order
      ON approval_steps (tenant_id, instance_id, step_order);
    CREATE INDEX ix_approval_steps_route_template_id
      ON approval_steps (route_template_id) WHERE instance_id IS NULL;
    CREATE INDEX ix_approval_steps_inbox
      ON approval_steps (tenant_id, approver_type, approver_ref, status);
    CREATE INDEX ix_approval_steps_tenant_id_due_at
      ON approval_steps (tenant_id, due_at) WHERE status = 'pending';

    REVOKE DELETE ON approval_steps FROM aip_app;
    """)

    op.execute("""
    ALTER TABLE workflow_instances
      ADD COLUMN route_template_id uuid NULL,
      ADD COLUMN current_step_id uuid NULL,
      ADD COLUMN route_round integer NOT NULL DEFAULT 0,
      ADD COLUMN route_submitted_by uuid NULL,
      ADD CONSTRAINT fk_workflow_instances_route_template
        FOREIGN KEY (route_template_id, tenant_id)
        REFERENCES approval_route_templates (id, tenant_id),
      ADD CONSTRAINT ck_workflow_instances_route_round CHECK (route_round >= 0);

    CREATE INDEX ix_workflow_instances_tenant_id_current_step_id
      ON workflow_instances (tenant_id, current_step_id);
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
