"""identity_invites

IDENTITY-04 (ADR 0005 rev 2, ADR 0010): invitations, MFA enrolment and sign-off assurance.

- ``user_invite`` (tenant template, FORCE RLS): one row per invitation. Keycloak sends the email
  and holds the password and second factor; the app keeps only who was invited, how and the
  status. At most one live (``pending``/``sent``) invite per email per tenant: re-inviting revokes
  the previous one first. ``aip_app`` has no DELETE (invites are revoked, never deleted).
- ``app_user.mfa_enrolled_at``: set the first time a session with ``aal = 2`` is issued for the
  user, cleared by an admin MFA reset (ACCESS-05 shows it).
- ``signoff_policy`` (tenant template, FORCE RLS): the tenant's minimum assurance per critical
  action (ADR 0010). The task spec keyed it ``(tenant_id, action_code)``; it uses the standard
  uuid key and soft delete instead (AGENTS.md hard rules), with ``(tenant_id, action_code)``
  unique among live rows.
- ``aip_jobs`` gets the narrow grants the invite job needs (OPS-17 has not decided how handlers
  write tenant tables yet): SELECT and UPDATE on ``user_invite``, SELECT and a column UPDATE on
  ``app_user`` (``keycloak_user_id``, ``updated_at``, ``sync_version``), INSERT on ``auth_event``.
  RLS still binds the handler to the job's tenant (the policies apply to every role).
- ``identity_register_email`` now also refuses an address whose domain an SSO IdP claims in
  ``login_directory`` (IDENTITY-02 security review): such people sign in through their company
  IdP, and a local claim would pin the address to one tenant and leak it to another's invite.

Revision ID: 202610181000
Revises: 202610171000
Create Date: 2026-10-18 10:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610181000"
down_revision: str | None = "202610171000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="user_invite",
            columns=(
                "user_id uuid NOT NULL, email citext NOT NULL, user_class text NOT NULL, "
                "organisation_id uuid NULL, invited_by uuid NULL, method text NOT NULL, "
                "keycloak_user_id uuid NULL, status text NOT NULL, last_error text NULL, "
                "expires_at timestamptz NOT NULL, sent_at timestamptz NULL, "
                "accepted_at timestamptz NULL, revoked_at timestamptz NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE user_invite
      ADD CONSTRAINT ck_user_invite_method CHECK (method IN ('local', 'sso')),
      ADD CONSTRAINT ck_user_invite_status
        CHECK (status IN ('pending', 'sent', 'accepted', 'revoked', 'failed')),
      ADD CONSTRAINT ck_user_invite_user_class CHECK (user_class IN ('staff', 'field', 'portal')),
      ADD CONSTRAINT ck_user_invite_last_error CHECK (char_length(last_error) <= 500),
      ADD CONSTRAINT fk_user_invite_user_id_tenant_id_app_user
        FOREIGN KEY (user_id, tenant_id) REFERENCES app_user (id, tenant_id),
      ADD CONSTRAINT fk_user_invite_invited_by_tenant_id_app_user
        FOREIGN KEY (invited_by, tenant_id) REFERENCES app_user (id, tenant_id);

    CREATE UNIQUE INDEX ux_user_invite_live_email ON user_invite (tenant_id, email)
      WHERE status IN ('pending', 'sent') AND deleted_at IS NULL;
    CREATE INDEX ix_user_invite_tenant_id_user_id ON user_invite (tenant_id, user_id);

    REVOKE DELETE ON user_invite FROM aip_app;
    """)

    op.execute("ALTER TABLE app_user ADD COLUMN mfa_enrolled_at timestamptz NULL;")

    op.execute(
        render_template(
            "tenant_table",
            table="signoff_policy",
            columns=(
                "action_code text NOT NULL, min_aal smallint NOT NULL, "
                "step_up_max_age_min smallint NOT NULL DEFAULT 10, updated_by uuid NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE signoff_policy
      ADD CONSTRAINT ck_signoff_policy_min_aal CHECK (min_aal IN (1, 2)),
      ADD CONSTRAINT ck_signoff_policy_step_up_max_age_min
        CHECK (step_up_max_age_min BETWEEN 1 AND 60),
      ADD CONSTRAINT ck_signoff_policy_action_code
        CHECK (action_code ~ '^[a-z][a-z0-9_]*(\\.[a-z0-9_]+)+$');

    CREATE UNIQUE INDEX ux_signoff_policy_tenant_id_action_code
      ON signoff_policy (tenant_id, action_code) WHERE deleted_at IS NULL;

    REVOKE DELETE ON signoff_policy FROM aip_app;
    """)

    op.execute("""
    GRANT SELECT, UPDATE ON user_invite TO aip_jobs;
    GRANT SELECT ON app_user TO aip_jobs;
    GRANT UPDATE (keycloak_user_id, updated_at, sync_version) ON app_user TO aip_jobs;
    GRANT INSERT ON auth_event TO aip_jobs;
    """)

    # contract: 202610181000 - SECURITY DEFINER on purpose (ADR 0005), replacing IDENTITY-02's
    # function with one more refusal: an email whose domain an SSO IdP claims is never registered
    # as a local account (EMAIL_DOMAIN_SSO). Same owner, search_path and grants as before.
    op.execute("""
    CREATE OR REPLACE FUNCTION identity_register_email(p_email citext, p_tenant uuid)
    RETURNS void
    LANGUAGE plpgsql
    VOLATILE
    SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $fn$
    DECLARE
      v_owner uuid;
    BEGIN
      IF p_tenant IS NULL OR p_email IS NULL
         OR p_tenant IS DISTINCT FROM NULLIF(current_setting('app.tenant_id', true), '')::uuid THEN
        RAISE EXCEPTION 'TENANT_CONTEXT_MISMATCH' USING ERRCODE = '42501';
      END IF;
      IF NOT EXISTS (
        SELECT 1 FROM public.app_user AS u
        WHERE u.tenant_id = p_tenant AND u.email = p_email
          AND u.deleted_at IS NULL AND NOT u.sso_managed
      ) THEN
        RAISE EXCEPTION 'EMAIL_NOT_A_LOCAL_USER' USING ERRCODE = '42501';
      END IF;
      IF EXISTS (
        SELECT 1 FROM public.login_directory AS d
        WHERE d.kind = 'email_domain'
          AND d.key = lower(split_part(p_email::text, '@', 2))::citext
          AND d.idp_alias IS NOT NULL
      ) THEN
        RAISE EXCEPTION 'EMAIL_DOMAIN_SSO' USING ERRCODE = 'P0001';
      END IF;
      INSERT INTO public.login_directory (kind, key, tenant_id, idp_alias)
      VALUES ('email', p_email, p_tenant, NULL)
      ON CONFLICT (kind, key) DO NOTHING;
      SELECT d.tenant_id INTO v_owner
      FROM public.login_directory AS d
      WHERE d.kind = 'email' AND d.key = p_email;
      IF v_owner IS DISTINCT FROM p_tenant THEN
        RAISE EXCEPTION 'EMAIL_IN_OTHER_TENANT' USING ERRCODE = 'P0001';
      END IF;
    END;
    $fn$;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
