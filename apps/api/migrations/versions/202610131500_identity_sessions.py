"""identity_sessions

IDENTITY-03 (ADR 0005 rev 2): the app issues every browser session itself.

- ``user_session`` (tenant template, FORCE RLS): one row per opaque ``__Host-aip_sid`` cookie. Only
  ``sid_hash`` (SHA-256 of the cookie value) is stored. ``idle_seconds`` is the idle window fixed
  at issue time from the tenant's policy, so sliding the idle expiry needs no policy read.
  Sessions are revoked, never deleted (``aip_app`` has no DELETE).
- ``tenant_auth_policy`` (FORCE RLS, keyed by ``tenant_id``): the single owner of session policy.
  A tenant without a row uses the defaults in ``identity.sessions.DEFAULT_POLICY``.
- ``identity_resolve_session`` and ``identity_sessions_by_kc_sid``: SECURITY DEFINER lookups for
  the two places that run before the tenant is known (the session cookie, Keycloak's back-channel
  logout). They run as the owner, so ``user_session`` gets a SELECT-only policy for ``aip_owner``
  (the precedent is ``domain_events``' ``dispatcher_select``); they return only live,
  unexpired, unrevoked sessions. Whether the user is still active is checked afterwards inside
  the tenant's own transaction (RLS on), not here.

Revision ID: 202610131500
Revises: 202610131400
Create Date: 2026-10-13 15:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610131500"
down_revision: str | None = "202610131400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="user_session",
            columns=(
                "user_id uuid NOT NULL, sid_hash bytea NOT NULL, audience text NOT NULL, "
                "device_id uuid NULL, aal smallint NOT NULL, amr text[] NOT NULL, "
                "authenticated_at timestamptz NOT NULL, kc_sid text NULL, ip inet NULL, "
                "user_agent text NULL, last_seen_at timestamptz NOT NULL DEFAULT now(), "
                "idle_seconds integer NOT NULL, idle_expires_at timestamptz NOT NULL, "
                "absolute_expires_at timestamptz NOT NULL, revoked_at timestamptz NULL, "
                "revoke_reason text NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE user_session
      ADD CONSTRAINT uq_user_session_sid_hash UNIQUE (sid_hash),
      ADD CONSTRAINT ck_user_session_sid_hash CHECK (octet_length(sid_hash) = 32),
      ADD CONSTRAINT ck_user_session_audience CHECK (audience IN ('app', 'portal', 'device')),
      ADD CONSTRAINT ck_user_session_aal CHECK (aal IN (1, 2)),
      ADD CONSTRAINT ck_user_session_idle_seconds CHECK (idle_seconds > 0),
      ADD CONSTRAINT ck_user_session_expiry CHECK (idle_expires_at <= absolute_expires_at),
      ADD CONSTRAINT ck_user_session_revoked
        CHECK ((revoked_at IS NULL) = (revoke_reason IS NULL)),
      ADD CONSTRAINT ck_user_session_user_agent CHECK (char_length(user_agent) <= 512),
      ADD CONSTRAINT fk_user_session_user_id_tenant_id_app_user
        FOREIGN KEY (user_id, tenant_id) REFERENCES app_user (id, tenant_id);

    CREATE INDEX ix_user_session_kc_sid ON user_session (kc_sid) WHERE revoked_at IS NULL;
    CREATE INDEX ix_user_session_tenant_id_user_id ON user_session (tenant_id, user_id)
      WHERE revoked_at IS NULL;

    REVOKE DELETE ON user_session FROM aip_app;
    """)

    op.execute("""
    CREATE TABLE tenant_auth_policy (
      tenant_id uuid NOT NULL,
      session_policy jsonb NOT NULL DEFAULT '{"staff": {"idleMin": 30, "absoluteH": 12},
        "field": {"idleMin": 5, "absoluteH": 12}, "portal": {"idleMin": 15, "absoluteH": 8}}',
      sso_enforced boolean NOT NULL DEFAULT false,
      step_up_max_age_min integer NOT NULL DEFAULT 10,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      deleted_at timestamptz NULL,
      CONSTRAINT pk_tenant_auth_policy PRIMARY KEY (tenant_id),
      CONSTRAINT fk_tenant_auth_policy_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      CONSTRAINT ck_tenant_auth_policy_session_policy
        CHECK (jsonb_typeof(session_policy) = 'object'),
      CONSTRAINT ck_tenant_auth_policy_step_up_max_age_min
        CHECK (step_up_max_age_min BETWEEN 1 AND 1440)
    );

    ALTER TABLE tenant_auth_policy ENABLE ROW LEVEL SECURITY;
    ALTER TABLE tenant_auth_policy FORCE ROW LEVEL SECURITY;
    CREATE POLICY tenant_isolation ON tenant_auth_policy
      FOR ALL
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

    GRANT SELECT, INSERT, UPDATE ON tenant_auth_policy TO aip_app;
    GRANT SELECT ON tenant_auth_policy TO aip_readonly;
    """)

    # contract: 202610131500 the owner-only SELECT policy below exists for the two SECURITY DEFINER
    # lookups (they run as the owner, and FORCE RLS applies to the owner too); aip_app is
    # unaffected.
    op.execute("CREATE POLICY session_lookup ON user_session FOR SELECT TO aip_owner USING (true)")

    # contract: 202610131500 SECURITY DEFINER lookups that run before the tenant is known (the
    # session cookie, the Keycloak back-channel logout). They read only live sessions of active
    # users and return no data beyond what the caller needs to bind the tenant.
    op.execute("""
    CREATE FUNCTION identity_resolve_session(p_sid_hash bytea)
    RETURNS TABLE (
      tenant_id uuid, user_id uuid, session_id uuid, aal smallint, amr text[],
      authenticated_at timestamptz, audience text, last_seen_at timestamptz,
      idle_seconds integer, idle_expires_at timestamptz, absolute_expires_at timestamptz
    )
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $$
      SELECT s.tenant_id, s.user_id, s.id, s.aal, s.amr, s.authenticated_at, s.audience,
             s.last_seen_at, s.idle_seconds, s.idle_expires_at, s.absolute_expires_at
      FROM user_session s
      WHERE s.sid_hash = p_sid_hash
        AND s.revoked_at IS NULL AND s.deleted_at IS NULL
        AND s.idle_expires_at > now() AND s.absolute_expires_at > now()
    $$;

    CREATE FUNCTION identity_sessions_by_kc_sid(p_kc_sid text)
    RETURNS TABLE (tenant_id uuid, session_id uuid)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $$
      SELECT s.tenant_id, s.id FROM user_session s
      WHERE s.kc_sid = p_kc_sid AND s.revoked_at IS NULL AND s.deleted_at IS NULL
    $$;

    REVOKE ALL ON FUNCTION identity_resolve_session(bytea) FROM PUBLIC;
    REVOKE ALL ON FUNCTION identity_sessions_by_kc_sid(text) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION identity_resolve_session(bytea) TO aip_app;
    GRANT EXECUTE ON FUNCTION identity_sessions_by_kc_sid(text) TO aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
