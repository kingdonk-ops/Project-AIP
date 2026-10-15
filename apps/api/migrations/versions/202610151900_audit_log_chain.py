"""audit_log_chain

AUDIT-01 (ADR 0002, ADR 0021, ADR 0031): the tamper-evident audit store.

- ``audit_log``: append-only, per-tenant, per-stream hash-chained event log. No ``updated_at`` and
  no ``deleted_at`` (a correction is a new row with ``supersedes_id``, never an edit). It is **not**
  range-partitioned: the chain needs a table-wide ``UNIQUE (tenant_id, stream, seq)`` and a partial
  ``UNIQUE (tenant_id, source_event_id)``, which a native partition's unique indexes cannot provide
  without the partition key (ADR 0031). A ``BEFORE UPDATE OR DELETE`` trigger raises
  ``audit_log is append-only`` so even the owner cannot rewrite the chain by accident; UPDATE,
  DELETE and TRUNCATE are also revoked from PUBLIC and every runtime role.
- ``audit_chain_heads``: the current ``(last_seq, last_hash)`` per ``(tenant_id, stream)``, locked
  ``FOR UPDATE`` to serialise appends.
- ``audit_chain_checkpoints``: the closing ``(last_seq, last_hash)`` of each monthly segment
  (ADR 0021), so verification can start from any checkpoint and an old segment can be removed by
  the AUDIT-05 retention job without breaking the rest of the chain.

Only ``aip_audit_writer`` may INSERT into ``audit_log`` and maintain the heads and checkpoints;
``aip_app`` and ``aip_readonly`` get SELECT only. The role is created by the superuser cluster
bootstrap (``db/bootstrap/00_cluster.sql``, ADR 0012); this revision verifies it is present and
unprivileged, then grants it.

Revision ID: 202610151900
Revises: 202610151800
Create Date: 2026-10-15 19:00:00+00:00
"""

from alembic import op

revision: str = "202610151900"
down_revision: str | None = "202610151800"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The audit writer role is a cluster object (ADR 0012): the bootstrap creates it, this revision
    # only verifies and grants. The ::regrole cast fails with "role ... does not exist" when it is
    # missing; the second query raises if it is privileged or cannot log in.
    op.execute("""
    SELECT 'aip_audit_writer'::regrole;
    -- One output row (and so a failing cast whose error names the role) only if it is wrong. The
    -- string_agg is NULL when no row matches, so the cast yields NULL rather than raising then.
    SELECT (
      'aip_audit_writer is privileged, cannot log in or can become aip_owner; rerun '
      || 'db/bootstrap/00_cluster.sql as a superuser: ' || string_agg(rolname, ', ')
    )::int
    FROM pg_roles
    WHERE rolname = 'aip_audit_writer'
      AND (NOT rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication
           OR rolbypassrls OR pg_has_role(oid, 'aip_owner', 'MEMBER'))
    HAVING count(*) > 0;
    GRANT USAGE ON SCHEMA public TO aip_audit_writer;
    """)

    # --- audit_log ---------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE audit_log (
      id uuid NOT NULL,
      tenant_id uuid NOT NULL,
      stream text NOT NULL,
      seq bigint NOT NULL,
      project_id uuid NULL,
      asset_id uuid NULL,
      asset_path ltree NULL,
      actor_id uuid NULL,
      on_behalf_of_id uuid NULL,
      auth_strength text NULL,
      source_module text NULL,
      record_table text NULL,
      record_id uuid NULL,
      event_type text NOT NULL,
      summary_key text NULL,
      payload jsonb NULL,
      reason_for_change text NULL,
      flags text[] NOT NULL DEFAULT '{}',
      source_ip inet NULL,
      device text NULL,
      source_event_id uuid NULL,
      supersedes_id uuid NULL,
      prev_hash bytea NOT NULL,
      hash bytea NOT NULL,
      occurred_at timestamptz NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT pk_audit_log PRIMARY KEY (id),
      CONSTRAINT uq_audit_log_tenant_id_stream_seq UNIQUE (tenant_id, stream, seq),
      CONSTRAINT ck_audit_log_stream CHECK (stream IN ('audit', 'security')),
      CONSTRAINT ck_audit_log_seq CHECK (seq > 0),
      CONSTRAINT ck_audit_log_event_type CHECK (event_type <> ''),
      CONSTRAINT ck_audit_log_prev_hash CHECK (octet_length(prev_hash) = 32),
      CONSTRAINT ck_audit_log_hash CHECK (octet_length(hash) = 32)
    );

    CREATE UNIQUE INDEX uq_audit_log_tenant_id_source_event_id
      ON audit_log (tenant_id, source_event_id) WHERE source_event_id IS NOT NULL;
    CREATE INDEX ix_audit_log_tenant_id_project_id_occurred_at
      ON audit_log (tenant_id, project_id, occurred_at DESC);
    CREATE INDEX ix_audit_log_record_table_record_id_occurred_at
      ON audit_log (record_table, record_id, occurred_at);
    CREATE INDEX ix_audit_log_tenant_id_actor_id_occurred_at
      ON audit_log (tenant_id, actor_id, occurred_at);
    CREATE INDEX ix_audit_log_asset_path ON audit_log USING gist (asset_path);
    CREATE INDEX ix_audit_log_flags ON audit_log USING gin (flags) WHERE flags <> '{}';

    ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
    ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON audit_log
      FOR ALL
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
    """)

    # The append-only guard: block UPDATE and DELETE at row level even for the owner, which FORCE
    # RLS otherwise lets through. Not SECURITY DEFINER; it only raises.
    op.execute("""
    CREATE FUNCTION audit_log_forbid_mutation()
    RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog
    AS $fn$
    BEGIN
      RAISE EXCEPTION 'audit_log is append-only' USING ERRCODE = 'restrict_violation';
    END
    $fn$;

    CREATE TRIGGER audit_log_append_only
      BEFORE UPDATE OR DELETE ON audit_log
      FOR EACH ROW EXECUTE FUNCTION audit_log_forbid_mutation();
    """)

    # Grants: only the writer inserts; the app and reporting may read. UPDATE/DELETE/TRUNCATE are
    # taken from PUBLIC and every role (the owner is stopped by the trigger instead).
    op.execute("""
    REVOKE UPDATE, DELETE, TRUNCATE ON audit_log
      FROM PUBLIC, aip_app, aip_jobs, aip_readonly, aip_audit_writer;
    GRANT SELECT, INSERT ON audit_log TO aip_audit_writer;
    GRANT SELECT ON audit_log TO aip_app, aip_readonly;
    """)

    # --- audit_chain_heads -------------------------------------------------------------------
    op.execute("""
    CREATE TABLE audit_chain_heads (
      tenant_id uuid NOT NULL,
      stream text NOT NULL,
      last_seq bigint NOT NULL DEFAULT 0,
      last_hash bytea NOT NULL,
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT pk_audit_chain_heads PRIMARY KEY (tenant_id, stream),
      CONSTRAINT ck_audit_chain_heads_stream CHECK (stream IN ('audit', 'security')),
      CONSTRAINT ck_audit_chain_heads_last_seq CHECK (last_seq >= 0),
      CONSTRAINT ck_audit_chain_heads_last_hash CHECK (octet_length(last_hash) = 32)
    );

    ALTER TABLE audit_chain_heads ENABLE ROW LEVEL SECURITY;
    ALTER TABLE audit_chain_heads FORCE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON audit_chain_heads
      FOR ALL
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

    REVOKE UPDATE, DELETE, TRUNCATE ON audit_chain_heads
      FROM PUBLIC, aip_app, aip_jobs, aip_readonly, aip_audit_writer;
    GRANT SELECT, INSERT, UPDATE ON audit_chain_heads TO aip_audit_writer;
    GRANT SELECT ON audit_chain_heads TO aip_readonly;
    """)

    # --- audit_chain_checkpoints -------------------------------------------------------------
    op.execute("""
    CREATE TABLE audit_chain_checkpoints (
      tenant_id uuid NOT NULL,
      stream text NOT NULL,
      segment text NOT NULL,
      last_seq bigint NOT NULL,
      last_hash bytea NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT pk_audit_chain_checkpoints PRIMARY KEY (tenant_id, stream, segment),
      CONSTRAINT ck_audit_chain_checkpoints_stream CHECK (stream IN ('audit', 'security')),
      CONSTRAINT ck_audit_chain_checkpoints_segment CHECK (segment ~ '^\\d{4}-\\d{2}$'),
      CONSTRAINT ck_audit_chain_checkpoints_last_seq CHECK (last_seq > 0),
      CONSTRAINT ck_audit_chain_checkpoints_last_hash CHECK (octet_length(last_hash) = 32)
    );

    ALTER TABLE audit_chain_checkpoints ENABLE ROW LEVEL SECURITY;
    ALTER TABLE audit_chain_checkpoints FORCE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON audit_chain_checkpoints
      FOR ALL
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

    REVOKE UPDATE, DELETE, TRUNCATE ON audit_chain_checkpoints
      FROM PUBLIC, aip_app, aip_jobs, aip_readonly, aip_audit_writer;
    GRANT SELECT, INSERT, UPDATE ON audit_chain_checkpoints TO aip_audit_writer;
    GRANT SELECT ON audit_chain_checkpoints TO aip_app, aip_readonly;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
