"""inspections_acknowledgements

INSPECTIONS-10 (ADR 0041 §3-§6, ADR 0031, DATABASE-05): the section and report acknowledgements
("Section complete", "Report complete") that lock an inspection's answers, and the template's
supervisor-review setting copied onto each inspection.

- ``inspections.has_supervisor_review`` is copied from the form template when the inspection is
  created and never changes afterwards; it decides which submit action the record offers.
- ``inspection_acknowledgements`` is append-only, from ``db/templates/append_only_table.sql.tpl``
  (monthly range partitions on ``created_at``, FORCE RLS fail closed, ``aip_app`` SELECT and INSERT
  only). Each tick, untick and rework clearing is one row; a scope's lock is its latest row.
  ``section_key`` is set exactly when ``scope = 'section'``.
- No foreign key to ``inspections``, for the reason ``202611011400_inspections_responses`` gives:
  the service writes only for an inspection it has locked in the caller's tenant.
- The view ``inspection_current_acknowledgements`` is the latest row per ``(inspection_id, scope,
  section_key)``; ``security_invoker`` so the caller's RLS applies. The service writes
  ``acted_at = created_at = clock_timestamp()`` after the inspection row lock, so the latest row
  always sorts last; ``id DESC`` (UUIDv7) only breaks a tie.
- Registered in ``partition_settings`` here, so ``ensure_partitions`` keeps partitions ahead.

Revision ID: 202611031000
Revises: 202611021000
Create Date: 2026-11-03 10:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202611031000"
down_revision: str | None = "202611021000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE inspections
      ADD COLUMN has_supervisor_review boolean NOT NULL DEFAULT true;
    """)
    op.execute(
        render_template(
            "append_only_table",
            table="inspection_acknowledgements",
            columns=(
                "inspection_id uuid NOT NULL, scope text NOT NULL, section_key text NULL, "
                "action text NOT NULL, actor uuid NOT NULL, revision_id uuid NOT NULL, "
                "acted_at timestamptz NOT NULL"
            ),
            partition_column="created_at",
        )
    )
    op.execute("""
    ALTER TABLE inspection_acknowledgements
      ADD CONSTRAINT ck_inspection_acknowledgements_scope
        CHECK (scope IN ('section', 'report')),
      ADD CONSTRAINT ck_inspection_acknowledgements_section_key
        CHECK ((scope = 'section') = (section_key IS NOT NULL)),
      ADD CONSTRAINT ck_inspection_acknowledgements_section_key_format
        CHECK (section_key IS NULL OR section_key ~ '^[a-z][a-z0-9_]{0,62}$'),
      ADD CONSTRAINT ck_inspection_acknowledgements_action
        CHECK (action IN ('tick', 'untick', 'cleared_by_rework'));

    CREATE INDEX ix_inspection_acknowledgements_current
      ON inspection_acknowledgements
        (tenant_id, inspection_id, scope, section_key, created_at DESC, id DESC);

    -- The template already revokes these; restated so the append-only rule reads in one place.
    REVOKE UPDATE, DELETE, TRUNCATE ON inspection_acknowledgements
      FROM aip_app, aip_jobs, aip_readonly;

    INSERT INTO partition_settings (table_name) VALUES ('inspection_acknowledgements');

    CREATE VIEW inspection_current_acknowledgements WITH (security_invoker = true) AS
      SELECT DISTINCT ON (inspection_id, scope, section_key)
        id, tenant_id, inspection_id, scope, section_key, action, actor, revision_id, acted_at,
        created_at
      FROM inspection_acknowledgements
      ORDER BY inspection_id, scope, section_key, created_at DESC, id DESC;

    GRANT SELECT ON inspection_current_acknowledgements TO aip_app, aip_readonly;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
