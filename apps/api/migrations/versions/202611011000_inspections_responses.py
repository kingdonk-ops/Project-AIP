"""inspections_responses

INSPECTIONS-02 (ADR 0002, DATABASE-05, ADR 0031, ADR 0041 §6): every answer an inspector gives is
one append-only ``inspection_responses`` row, from ``db/templates/append_only_table.sql.tpl``
(monthly range partitions on ``created_at``, FORCE RLS fail closed, ``aip_app`` SELECT and INSERT
only). A correction is a new row whose ``supersedes_id`` names the row that was current before.

- ``client_id`` makes a retried push idempotent. It cannot be unique table-wide on a partitioned
  table (ADR 0031), so the service serialises writes per inspection (``FOR UPDATE`` on the
  inspection) and looks it up through ``ix_inspection_responses_client_id``.
- No foreign key to ``inspections``: ``aip_ensure_partitions`` attaches each new month by
  validating a cloned foreign key under FORCE RLS without a tenant, which sees no parent rows and
  fails once the default partition holds answers. The service writes only for an inspection it
  has locked in the caller's tenant.
- The view ``inspection_current_responses`` is the latest row per field. It is
  ``security_invoker`` so the caller's RLS applies. The service writes ``created_at`` as
  ``clock_timestamp()`` after the row lock, so the latest answer always sorts last; ``id DESC``
  (UUIDv7) only breaks a tie.
- Registered in ``partition_settings`` here, so ``ensure_partitions`` keeps partitions ahead.

Revision ID: 202611011000
Revises: 202610311900
Create Date: 2026-11-01 10:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202611011000"
down_revision: str | None = "202610311900"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        render_template(
            "append_only_table",
            table="inspection_responses",
            columns=(
                "inspection_id uuid NOT NULL, field_key text NOT NULL, value jsonb NULL, "
                "failed boolean NOT NULL, revision_id uuid NOT NULL, client_id uuid NOT NULL, "
                "supersedes_id uuid NULL, responded_by uuid NOT NULL, "
                "responded_at timestamptz NOT NULL"
            ),
            partition_column="created_at",
        )
    )
    op.execute("""
    ALTER TABLE inspection_responses
      ADD CONSTRAINT ck_inspection_responses_field_key
        CHECK (field_key ~ '^[a-z][a-z0-9_]{0,62}$');

    CREATE INDEX ix_inspection_responses_current
      ON inspection_responses (tenant_id, inspection_id, field_key, created_at DESC, id DESC);
    CREATE INDEX ix_inspection_responses_client_id
      ON inspection_responses (tenant_id, inspection_id, client_id);

    -- The template already revokes these; restated so the append-only rule reads in one place.
    REVOKE UPDATE, DELETE, TRUNCATE ON inspection_responses FROM aip_app, aip_jobs, aip_readonly;

    INSERT INTO partition_settings (table_name) VALUES ('inspection_responses');

    CREATE VIEW inspection_current_responses WITH (security_invoker = true) AS
      SELECT DISTINCT ON (inspection_id, field_key)
        id, tenant_id, inspection_id, field_key, value, failed, revision_id, responded_by,
        responded_at, created_at
      FROM inspection_responses
      ORDER BY inspection_id, field_key, created_at DESC, id DESC;

    GRANT SELECT ON inspection_current_responses TO aip_app, aip_readonly;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
