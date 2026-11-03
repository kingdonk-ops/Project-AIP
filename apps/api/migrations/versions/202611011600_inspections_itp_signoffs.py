"""inspections_itp_signoffs

INSPECTIONS-03 (ADR 0010, ADR 0031, ADR 0035): ITP steps with hold, witness, review and
surveillance points, and the append-only, hash-chained sign-offs that release them.

- ``itp_steps`` (``tenant_table`` with the offline-sync columns): one ordered step of an ITP-kind
  inspection. ``asset_id`` is copied from the ITP. ``task_id``/``blocks_task_id`` (scope tasks)
  and ``hold_flag_issue_id`` (an issues NCR) are plain uuids: those modules link them through
  ``InspectionsApi``. ``notice_hours`` belongs to witness points only. Steps are soft-deleted, so
  ``aip_app`` loses DELETE.
- ``inspection_signoffs``: one row per release, witness, waiver or rejection, ``seq`` counting
  from 1 per inspection (``unique (inspection_id, seq)``) and ``prev_hash``/``entry_hash`` the
  chain (``signoff_chain.py``). ``status`` is ``applied`` or ``pending_countersign`` (ADR 0010);
  the countersign is a later ``applied`` row whose ``countersigns_id`` names it. Not
  range-partitioned, for the ADR 0031 reason (the table-wide unique key needs no partition key),
  so it is not in ``partition_settings``. No ``updated_at``/``deleted_at``: ``aip_app`` may only
  SELECT and INSERT, and UPDATE, DELETE and TRUNCATE are revoked from every runtime role.
  ``signatory_role`` has no ``client`` until INSPECTIONS-05 (OPEN-QUESTIONS #42);
  ``eligibility_result`` stays NULL until INSPECTIONS-07. Kept 7 years (ADR 0021).

Revision ID: 202611011600
Revises: 202611011500
Create Date: 2026-11-01 16:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202611011600"
down_revision: str | None = "202611011500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="itp_steps",
            columns=(
                "inspection_id uuid NOT NULL, asset_id uuid NOT NULL, seq integer NOT NULL, "
                "title text NOT NULL, point_type text NOT NULL, acceptance_criteria text NULL, "
                "task_id uuid NULL, blocks_task_id uuid NULL, child_inspection_id uuid NULL, "
                "status text NOT NULL, hold_flag_issue_id uuid NULL, "
                "notice_hours integer NULL, ready_at timestamptz NULL, "
                "released_at timestamptz NULL"
            ),
            sync=True,
        )
    )
    op.execute("""
    ALTER TABLE itp_steps
      ALTER COLUMN status SET DEFAULT 'pending',
      ADD CONSTRAINT fk_itp_steps_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      ADD CONSTRAINT fk_itp_steps_inspection
        FOREIGN KEY (inspection_id, tenant_id) REFERENCES inspections (id, tenant_id),
      ADD CONSTRAINT fk_itp_steps_child_inspection
        FOREIGN KEY (child_inspection_id, tenant_id) REFERENCES inspections (id, tenant_id),
      ADD CONSTRAINT uq_itp_steps_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT ck_itp_steps_seq CHECK (seq >= 1),
      ADD CONSTRAINT ck_itp_steps_title CHECK (char_length(title) BETWEEN 1 AND 200),
      ADD CONSTRAINT ck_itp_steps_point_type
        CHECK (point_type IN ('hold', 'witness', 'review', 'surveillance')),
      ADD CONSTRAINT ck_itp_steps_status
        CHECK (status IN ('pending', 'ready', 'in_progress', 'released', 'waived', 'rejected')),
      ADD CONSTRAINT ck_itp_steps_notice_hours
        CHECK (notice_hours IS NULL OR (point_type = 'witness' AND notice_hours BETWEEN 0 AND 720));

    CREATE UNIQUE INDEX uq_itp_steps_tenant_id_inspection_id_seq
      ON itp_steps (tenant_id, inspection_id, seq) WHERE deleted_at IS NULL;
    CREATE INDEX ix_itp_steps_tenant_id_task_id ON itp_steps (tenant_id, task_id);
    CREATE INDEX ix_itp_steps_tenant_id_blocks_task_id
      ON itp_steps (tenant_id, blocks_task_id) WHERE point_type = 'hold';
    CREATE INDEX ix_itp_steps_tenant_id_asset_id ON itp_steps (tenant_id, asset_id);

    REVOKE DELETE ON itp_steps FROM aip_app;

    CREATE TABLE inspection_signoffs (
      id uuid NOT NULL,
      tenant_id uuid NOT NULL,
      inspection_id uuid NOT NULL,
      itp_step_id uuid NULL,
      asset_id uuid NOT NULL,
      seq integer NOT NULL,
      signatory_role text NOT NULL,
      signer_user_id uuid NOT NULL,
      decision text NOT NULL,
      action_code text NOT NULL,
      status text NOT NULL,
      countersigns_id uuid NULL,
      auth_strength text NOT NULL,
      assurance_level smallint NOT NULL,
      assurance_method text NOT NULL,
      authenticated_at timestamptz NULL,
      device_id uuid NULL,
      eligibility_result jsonb NULL,
      content_hash text NOT NULL,
      prev_hash text NOT NULL,
      entry_hash text NOT NULL,
      comment text NULL,
      signed_at timestamptz NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT pk_inspection_signoffs PRIMARY KEY (id),
      CONSTRAINT uq_inspection_signoffs_inspection_id_seq UNIQUE (inspection_id, seq),
      CONSTRAINT fk_inspection_signoffs_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      CONSTRAINT fk_inspection_signoffs_inspection
        FOREIGN KEY (inspection_id, tenant_id) REFERENCES inspections (id, tenant_id),
      CONSTRAINT fk_inspection_signoffs_itp_step
        FOREIGN KEY (itp_step_id, tenant_id) REFERENCES itp_steps (id, tenant_id),
      CONSTRAINT ck_inspection_signoffs_seq CHECK (seq >= 1),
      CONSTRAINT ck_inspection_signoffs_signatory_role
        CHECK (signatory_role IN ('inspector', 'supervisor', 'third_party')),
      CONSTRAINT ck_inspection_signoffs_decision
        CHECK (decision IN ('approve', 'reject', 'witnessed', 'waived')),
      CONSTRAINT ck_inspection_signoffs_status
        CHECK (status IN ('applied', 'pending_countersign')),
      CONSTRAINT ck_inspection_signoffs_auth_strength
        CHECK (auth_strength IN ('password', 'mfa', 'pin')),
      CONSTRAINT ck_inspection_signoffs_assurance_level CHECK (assurance_level IN (1, 2)),
      CONSTRAINT ck_inspection_signoffs_comment
        CHECK (comment IS NULL OR char_length(comment) <= 2000),
      CONSTRAINT ck_inspection_signoffs_content_hash CHECK (content_hash ~ '^[0-9a-f]{64}$'),
      CONSTRAINT ck_inspection_signoffs_prev_hash CHECK (prev_hash ~ '^[0-9a-f]{64}$'),
      CONSTRAINT ck_inspection_signoffs_entry_hash CHECK (entry_hash ~ '^[0-9a-f]{64}$')
    );

    CREATE INDEX ix_inspection_signoffs_tenant_id ON inspection_signoffs (tenant_id);
    CREATE INDEX ix_inspection_signoffs_tenant_id_inspection_id_signed_at
      ON inspection_signoffs (tenant_id, inspection_id, signed_at);
    CREATE INDEX ix_inspection_signoffs_tenant_id_signer_user_id
      ON inspection_signoffs (tenant_id, signer_user_id);
    CREATE INDEX ix_inspection_signoffs_tenant_id_asset_id
      ON inspection_signoffs (tenant_id, asset_id);
    CREATE INDEX ix_inspection_signoffs_itp_step_id ON inspection_signoffs (itp_step_id);

    ALTER TABLE inspection_signoffs ENABLE ROW LEVEL SECURITY;
    ALTER TABLE inspection_signoffs FORCE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON inspection_signoffs
      FOR ALL
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

    REVOKE UPDATE, DELETE, TRUNCATE ON inspection_signoffs
      FROM PUBLIC, aip_app, aip_jobs, aip_readonly;
    GRANT SELECT, INSERT ON inspection_signoffs TO aip_app;
    GRANT SELECT ON inspection_signoffs TO aip_readonly;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
