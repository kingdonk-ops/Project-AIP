"""security_tables

SECURITY-02: the security and compliance programme tables
(``docs/blueprint/modules/security/data-model.md``).

Mutable, from ``db/templates/tenant_table.sql.tpl`` (soft delete; ``aip_app`` loses DELETE):
``control_records``, ``access_reviews``, ``data_map_entries`` and ``breach_incidents``.

Append-only evidence, from ``db/templates/append_only_table.sql.tpl`` (monthly partitions on
``created_at``, registered in ``partition_settings``; ``aip_app`` has only SELECT and INSERT):
``evidence_items``, ``restore_test_records`` and ``provenance_entries``. Their PK is
``(id, created_at)``, so nothing can hold a FK to them; ``restore_test_records.evidence_item_id``
is a plain uuid. ``collected_at`` and ``recorded_at`` are the business times (they may predate
the insert); ``created_at`` is the insert time and the partition key.

All seven carry ``tenant_id`` (the operator tenant, or the customer tenant in a siloed stack)
with FORCE RLS and the fail-closed NULLIF policy from the templates. ``evidence_items`` points
at its control through ``(control_id, tenant_id)``, so evidence can never attach to another
tenant's control. Cross-module references (``users``, ``documents``) are plain uuid columns.

Revision ID: 202610151900
Revises: 202610151500
Create Date: 2026-10-15 19:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610151900"
down_revision: str | None = "202610151500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- control_records: the control catalogue and its status ------------------------------
    op.execute(
        render_template(
            "tenant_table",
            table="control_records",
            columns=(
                "control_key text NOT NULL, title text NOT NULL, "
                "framework_mappings jsonb NOT NULL, "
                "owner_user_id uuid NULL, status text NOT NULL, "
                "evidence_source text NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE control_records
      ALTER COLUMN framework_mappings SET DEFAULT '{}'::jsonb,
      ALTER COLUMN status SET DEFAULT 'specified';
    ALTER TABLE control_records
      ADD CONSTRAINT uq_control_records_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT ck_control_records_status
        CHECK (status IN ('specified', 'implemented', 'proven')),
      ADD CONSTRAINT ck_control_records_control_key CHECK (control_key <> ''),
      ADD CONSTRAINT ck_control_records_title CHECK (title <> ''),
      ADD CONSTRAINT ck_control_records_framework_mappings
        CHECK (jsonb_typeof(framework_mappings) = 'object');

    CREATE UNIQUE INDEX uq_control_records_tenant_id_control_key
      ON control_records (tenant_id, control_key) WHERE deleted_at IS NULL;
    CREATE INDEX ix_control_records_tenant_id_status ON control_records (tenant_id, status);

    REVOKE DELETE ON control_records FROM aip_app;
    """)

    # --- evidence_items: append-only artefacts collected against a control ------------------
    op.execute(
        render_template(
            "append_only_table",
            table="evidence_items",
            columns=(
                "control_id uuid NOT NULL, evidence_type text NOT NULL, "
                "document_id uuid NULL, storage_key text NULL, content_hash text NULL, "
                "collected_at timestamptz NOT NULL, "
                "period_start date NULL, period_end date NULL"
            ),
            partition_column="created_at",
        )
    )
    op.execute("""
    ALTER TABLE evidence_items
      ADD CONSTRAINT ck_evidence_items_evidence_type
        CHECK (evidence_type IN ('ci_artefact', 'screenshot', 'report', 'sign_off')),
      ADD CONSTRAINT ck_evidence_items_content_hash CHECK (content_hash ~ '^[0-9a-f]{64}$'),
      ADD CONSTRAINT ck_evidence_items_period CHECK (period_end >= period_start),
      ADD CONSTRAINT fk_evidence_items_control_id_tenant_id_control_records
        FOREIGN KEY (control_id, tenant_id) REFERENCES control_records (id, tenant_id);

    CREATE INDEX ix_evidence_items_tenant_id_control_id_collected_at
      ON evidence_items (tenant_id, control_id, collected_at DESC);
    """)

    # --- access_reviews: quarterly access review with sign-off --------------------------------
    op.execute(
        render_template(
            "tenant_table",
            table="access_reviews",
            columns=(
                "quarter text NOT NULL, status text NOT NULL, "
                "snapshot jsonb NOT NULL, decisions jsonb NOT NULL, "
                "signed_off_by uuid NULL, signed_off_at timestamptz NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE access_reviews
      ALTER COLUMN status SET DEFAULT 'open',
      ALTER COLUMN decisions SET DEFAULT '{}'::jsonb;
    ALTER TABLE access_reviews
      ADD CONSTRAINT ck_access_reviews_quarter CHECK (quarter ~ '^[0-9]{4}-Q[1-4]$'),
      ADD CONSTRAINT ck_access_reviews_status
        CHECK (status IN ('open', 'in_review', 'signed_off')),
      ADD CONSTRAINT ck_access_reviews_snapshot CHECK (jsonb_typeof(snapshot) = 'object'),
      ADD CONSTRAINT ck_access_reviews_decisions CHECK (jsonb_typeof(decisions) = 'object'),
      -- A signed-off review names who signed and when; the post-sign-off lock is SECURITY-05's.
      ADD CONSTRAINT ck_access_reviews_signed_off CHECK (
        (status = 'signed_off') = (signed_off_by IS NOT NULL AND signed_off_at IS NOT NULL)
      );

    CREATE UNIQUE INDEX uq_access_reviews_tenant_id_quarter
      ON access_reviews (tenant_id, quarter) WHERE deleted_at IS NULL;

    REVOKE DELETE ON access_reviews FROM aip_app;
    """)

    # --- restore_test_records: append-only restore test evidence -----------------------------
    op.execute(
        render_template(
            "append_only_table",
            table="restore_test_records",
            columns=(
                "environment text NOT NULL, backup_taken_at timestamptz NOT NULL, "
                "restore_started_at timestamptz NOT NULL, "
                "restore_completed_at timestamptz NULL, "
                "rpo_achieved_seconds integer NULL, rto_achieved_seconds integer NULL, "
                "result text NOT NULL, evidence_item_id uuid NULL, performed_by uuid NULL"
            ),
            partition_column="created_at",
        )
    )
    op.execute("""
    ALTER TABLE restore_test_records
      ADD CONSTRAINT ck_restore_test_records_environment CHECK (environment <> ''),
      ADD CONSTRAINT ck_restore_test_records_result CHECK (result IN ('pass', 'fail')),
      ADD CONSTRAINT ck_restore_test_records_rpo CHECK (rpo_achieved_seconds >= 0),
      ADD CONSTRAINT ck_restore_test_records_rto CHECK (rto_achieved_seconds >= 0),
      ADD CONSTRAINT ck_restore_test_records_completed
        CHECK (restore_completed_at >= restore_started_at);

    CREATE INDEX ix_restore_test_records_tenant_id_created_at
      ON restore_test_records (tenant_id, created_at DESC);
    """)

    # --- data_map_entries: the Privacy Act / APP data map --------------------------------------
    op.execute(
        render_template(
            "tenant_table",
            table="data_map_entries",
            columns=(
                "data_category text NOT NULL, classification text NOT NULL, "
                "system_location text NOT NULL, region text NOT NULL, purpose text NOT NULL, "
                "retention_rule text NOT NULL, sub_processor text NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE data_map_entries
      ADD CONSTRAINT ck_data_map_entries_classification
        CHECK (classification IN ('public', 'internal', 'sensitive', 'health')),
      ADD CONSTRAINT ck_data_map_entries_data_category CHECK (data_category <> '');

    CREATE INDEX ix_data_map_entries_tenant_id_classification
      ON data_map_entries (tenant_id, classification);

    REVOKE DELETE ON data_map_entries FROM aip_app;
    """)

    # --- breach_incidents: breach register with the NDB assessment clock ---------------------
    op.execute(
        render_template(
            "tenant_table",
            table="breach_incidents",
            columns=(
                "detected_at timestamptz NOT NULL, description text NOT NULL, "
                "data_categories jsonb NOT NULL, "
                "individuals_affected integer NULL, serious_harm_likely boolean NULL, "
                "assessment_due_at timestamptz NOT NULL, "
                "oaic_notified_at timestamptz NULL, individuals_notified_at timestamptz NULL, "
                "status text NOT NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE breach_incidents
      ALTER COLUMN data_categories SET DEFAULT '[]'::jsonb,
      ALTER COLUMN status SET DEFAULT 'open';
    ALTER TABLE breach_incidents
      ADD CONSTRAINT ck_breach_incidents_status
        CHECK (status IN ('open', 'assessing', 'notified', 'closed')),
      ADD CONSTRAINT ck_breach_incidents_data_categories
        CHECK (jsonb_typeof(data_categories) = 'array'),
      ADD CONSTRAINT ck_breach_incidents_individuals_affected CHECK (individuals_affected >= 0),
      ADD CONSTRAINT ck_breach_incidents_description CHECK (description <> '');

    CREATE INDEX ix_breach_incidents_tenant_id_status ON breach_incidents (tenant_id, status);
    -- The NDB clock sweep, run per tenant through with_tenant: open incidents by due time.
    CREATE INDEX ix_breach_incidents_tenant_id_assessment_due_at
      ON breach_incidents (tenant_id, assessment_due_at) WHERE status IN ('open', 'assessing');

    REVOKE DELETE ON breach_incidents FROM aip_app;
    """)

    # --- provenance_entries: append-only clean-room provenance log ---------------------------
    op.execute(
        render_template(
            "append_only_table",
            table="provenance_entries",
            columns=(
                "feature text NOT NULL, reference_source text NOT NULL, "
                "own_spec_path text NOT NULL, author text NOT NULL, "
                "legal_review_ref text NULL, recorded_at timestamptz NOT NULL"
            ),
            partition_column="created_at",
        )
    )
    op.execute("""
    ALTER TABLE provenance_entries
      ADD CONSTRAINT ck_provenance_entries_feature CHECK (feature <> ''),
      ADD CONSTRAINT ck_provenance_entries_author CHECK (author <> '');

    CREATE INDEX ix_provenance_entries_tenant_id_recorded_at
      ON provenance_entries (tenant_id, recorded_at DESC);
    """)

    # The templates already revoke these; restated so the append-only rule reads in one place.
    op.execute("""
    REVOKE UPDATE, DELETE, TRUNCATE ON evidence_items, restore_test_records, provenance_entries
      FROM aip_app, aip_jobs;

    INSERT INTO partition_settings (table_name)
    VALUES ('evidence_items'), ('restore_test_records'), ('provenance_entries');
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
