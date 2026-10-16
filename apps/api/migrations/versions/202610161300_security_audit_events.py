"""security_audit_events

AUDIT-02 (ADR 0021): the security stream, kept apart from ``audit_log`` because it has its own
retention (3 years) and is never shown in project timelines. Sign-ins, sessions, role and
permission changes, exports and recorded sensitive reads land here; ``user.deactivated`` lands in
both tables.

Append-only and hash-chained exactly like ``audit_log`` (AUDIT-01): its chain head and monthly
checkpoints are the ``stream = 'security'`` rows of ``audit_chain_heads`` and
``audit_chain_checkpoints``, which already allow that stream. A ``BEFORE UPDATE OR DELETE`` trigger
raises for every role including the owner; UPDATE, DELETE and TRUNCATE are revoked from PUBLIC and
every runtime role; only ``aip_audit_writer`` inserts; FORCE RLS on ``tenant_id``. There is no
mutable column (SIEM forwarding is out of scope). ``source_ip`` and ``device`` are stored for
querying and, unlike in ``audit_log``, are hashed: they are this stream's main forensic fields
(``aip.modules.audit.security_chain``). ``audit_log`` is narrowed to ``stream = 'audit'``, so the
``(tenant, 'security')`` chain head belongs to this table alone.

Revision ID: 202610161300
Revises: 202610161200
Create Date: 2026-10-16 13:00:00+00:00
"""

from alembic import op

revision: str = "202610161300"
down_revision: str | None = "202610161200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE security_audit_events (
      id uuid NOT NULL,
      tenant_id uuid NOT NULL,
      seq bigint NOT NULL,
      actor_id uuid NULL,
      event_type text NOT NULL,
      target_ref text NULL,
      auth_strength text NULL,
      source_ip inet NULL,
      device text NULL,
      detail jsonb NULL,
      source_event_id uuid NULL,
      prev_hash bytea NOT NULL,
      hash bytea NOT NULL,
      occurred_at timestamptz NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT pk_security_audit_events PRIMARY KEY (id),
      CONSTRAINT uq_security_audit_events_tenant_id_seq UNIQUE (tenant_id, seq),
      CONSTRAINT ck_security_audit_events_seq CHECK (seq > 0),
      CONSTRAINT ck_security_audit_events_event_type CHECK (event_type <> ''),
      CONSTRAINT ck_security_audit_events_prev_hash CHECK (octet_length(prev_hash) = 32),
      CONSTRAINT ck_security_audit_events_hash CHECK (octet_length(hash) = 32)
    );

    CREATE UNIQUE INDEX uq_security_audit_events_tenant_id_source_event_id
      ON security_audit_events (tenant_id, source_event_id) WHERE source_event_id IS NOT NULL;
    CREATE INDEX ix_security_audit_events_tenant_id_event_type_occurred_at
      ON security_audit_events (tenant_id, event_type, occurred_at);
    CREATE INDEX ix_security_audit_events_tenant_id_actor_id_occurred_at
      ON security_audit_events (tenant_id, actor_id, occurred_at);

    ALTER TABLE security_audit_events ENABLE ROW LEVEL SECURITY;
    ALTER TABLE security_audit_events FORCE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON security_audit_events
      FOR ALL
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
    """)

    # The append-only guard, as for audit_log: raises for every role, the owner included.
    op.execute("""
    CREATE FUNCTION security_audit_events_forbid_mutation()
    RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog
    AS $fn$
    BEGIN
      RAISE EXCEPTION 'security_audit_events is append-only' USING ERRCODE = 'restrict_violation';
    END
    $fn$;

    CREATE TRIGGER security_audit_events_append_only
      BEFORE UPDATE OR DELETE ON security_audit_events
      FOR EACH ROW EXECUTE FUNCTION security_audit_events_forbid_mutation();
    """)

    # No audit_log row has stream 'security' (nothing wrote it before this revision).
    op.execute("""
    ALTER TABLE audit_log DROP CONSTRAINT ck_audit_log_stream;
    ALTER TABLE audit_log ADD CONSTRAINT ck_audit_log_stream CHECK (stream = 'audit');
    """)

    op.execute("""
    REVOKE UPDATE, DELETE, TRUNCATE ON security_audit_events
      FROM PUBLIC, aip_app, aip_jobs, aip_readonly, aip_audit_writer;
    GRANT SELECT, INSERT ON security_audit_events TO aip_audit_writer;
    GRANT SELECT ON security_audit_events TO aip_app, aip_readonly;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
