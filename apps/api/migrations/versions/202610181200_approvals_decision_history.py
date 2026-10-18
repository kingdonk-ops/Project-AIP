"""approvals_decision_history

APPROVALS-02 (ADR 0002, ADR 0010, ADR 0035): the append-only, hash-chained decision log of every
workflow transition (``docs/blueprint/modules/approvals/data-model.md``).

- ``workflow_decision_history``: one row per decision, ``seq`` counting from 1 per instance
  (``unique (instance_id, seq)``), ``prev_hash``/``entry_hash`` the chain (64 hex characters each,
  ``decision_chain.py``). ``status`` is ``applied`` or ``pending_countersign`` (a critical
  decision whose signer's assurance was too low, ADR 0010); the countersign that makes it take
  effect is a later ``applied`` row whose ``countersigns_id`` names it. ``assurance_*``,
  ``authenticated_at`` and ``device_id`` record how the signer proved who they were.
  Not range-partitioned: the table-wide ``unique (instance_id, seq)`` needs no partition key
  (the ADR 0031 reasoning for ``audit_log``). No ``updated_at``/``deleted_at``; ``aip_app`` may only
  SELECT and INSERT, and UPDATE, DELETE and TRUNCATE are revoked from every runtime role.
- ``workflow_instances`` gains ``uq_workflow_instances_id_tenant_id`` so a decision can reference
  an instance in its own tenant only.

``step_id``, ``on_behalf_of`` and ``supersedes_id`` are plain uuids until APPROVALS-04 (steps,
delegations) and a correction flow exist.

Revision ID: 202610181200
Revises: 202610181000
Create Date: 2026-10-18 12:00:00+00:00
"""

from alembic import op

revision: str = "202610181200"
down_revision: str | None = "202610181000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE workflow_instances
      ADD CONSTRAINT uq_workflow_instances_id_tenant_id UNIQUE (id, tenant_id);

    CREATE TABLE workflow_decision_history (
      id uuid NOT NULL,
      tenant_id uuid NOT NULL,
      instance_id uuid NOT NULL,
      step_id uuid NULL,
      seq integer NOT NULL,
      from_state text NOT NULL,
      to_state text NOT NULL,
      action text NOT NULL,
      actor_id uuid NULL,
      on_behalf_of uuid NULL,
      comment text NULL,
      auth_strength text NULL,
      ip_address text NULL,
      guard_result jsonb NULL,
      supersedes_id uuid NULL,
      status text NOT NULL,
      countersigns_id uuid NULL,
      assurance_level smallint NULL,
      assurance_method text NULL,
      authenticated_at timestamptz NULL,
      device_id uuid NULL,
      prev_hash text NOT NULL,
      entry_hash text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT pk_workflow_decision_history PRIMARY KEY (id),
      CONSTRAINT uq_workflow_decision_history_instance_id_seq UNIQUE (instance_id, seq),
      CONSTRAINT fk_workflow_decision_history_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      CONSTRAINT fk_workflow_decision_history_instance
        FOREIGN KEY (instance_id, tenant_id) REFERENCES workflow_instances (id, tenant_id),
      CONSTRAINT ck_workflow_decision_history_seq CHECK (seq >= 1),
      CONSTRAINT ck_workflow_decision_history_status
        CHECK (status IN ('applied', 'pending_countersign')),
      CONSTRAINT ck_workflow_decision_history_auth_strength
        CHECK (auth_strength IS NULL OR auth_strength IN ('password', 'mfa', 'pin', 'stepup')),
      CONSTRAINT ck_workflow_decision_history_assurance_level
        CHECK (assurance_level IS NULL OR assurance_level IN (1, 2)),
      CONSTRAINT ck_workflow_decision_history_comment
        CHECK (comment IS NULL OR char_length(comment) <= 2000),
      CONSTRAINT ck_workflow_decision_history_prev_hash CHECK (prev_hash ~ '^[0-9a-f]{64}$'),
      CONSTRAINT ck_workflow_decision_history_entry_hash CHECK (entry_hash ~ '^[0-9a-f]{64}$')
    );

    CREATE INDEX ix_workflow_decision_history_tenant_id
      ON workflow_decision_history (tenant_id);
    CREATE INDEX ix_workflow_decision_history_tenant_id_actor_id_created_at
      ON workflow_decision_history (tenant_id, actor_id, created_at);

    ALTER TABLE workflow_decision_history ENABLE ROW LEVEL SECURITY;
    ALTER TABLE workflow_decision_history FORCE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON workflow_decision_history
      FOR ALL
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

    REVOKE UPDATE, DELETE, TRUNCATE ON workflow_decision_history
      FROM PUBLIC, aip_app, aip_jobs, aip_readonly;
    GRANT SELECT, INSERT ON workflow_decision_history TO aip_app;
    GRANT SELECT ON workflow_decision_history TO aip_readonly;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
