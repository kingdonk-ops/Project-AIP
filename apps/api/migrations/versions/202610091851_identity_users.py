"""identity_users

IDENTITY-02 (ADR 0002, 0005): ``app_user``, ``tenant_membership`` and the append-only
``auth_event``, plus local-account email registration in the pre-tenant ``login_directory``.

- ``app_user`` and ``tenant_membership`` come from ``db/templates/tenant_table.sql.tpl`` (uuid PK,
  ``tenant_id``, timestamps, soft delete, FORCE RLS with the fail-closed NULLIF policy, grants).
  The template's column list allows no quotes, so string CHECKs are added after it.
- There is no password hash or MFA column: Keycloak holds every staff credential (ADR 0005 rev 2).
  ``keycloak_user_id`` is the ID token ``sub``; ``idp_alias`` is NULL for a Keycloak-local account.
- Cross-row references are composite ``(x_id, tenant_id)`` foreign keys, so a membership or an
  auth event can never point at another tenant's user. Every ``tenant_id`` references ``tenants``.
- ``auth_event`` is append-only: written by hand with the same policy but without
  ``updated_at``/``deleted_at``; no runtime role is granted UPDATE or DELETE on it.
- ``login_directory.kind`` gains ``email``. ``identity_register_email`` (SECURITY DEFINER) maps a
  local account's email to exactly one tenant; the OIDC callback resolves the tenant of a local
  account from it when the email domain is unknown. The function only registers for the tenant
  bound to the current transaction (``app.tenant_id``) and only an email that a live local
  ``app_user`` of that tenant holds (FORCE RLS binds the owning role too), so one tenant cannot
  claim an arbitrary address. An email already registered to another tenant raises
  ``EMAIL_IN_OTHER_TENANT``.

Revision ID: 202610091851
Revises: 202610081200
Create Date: 2026-10-09 18:51:44.633679+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610091851"
down_revision: str | None = "202610081200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="app_user",
            columns=(
                "organisation_id uuid NULL, user_class text NOT NULL, email citext NOT NULL, "
                "display_name text NOT NULL, idp_alias text NULL, keycloak_user_id uuid NULL, "
                "external_id text NULL, sso_managed boolean NOT NULL DEFAULT false, "
                "status text NOT NULL, deactivated_at timestamptz NULL, "
                "last_login_at timestamptz NULL, sync_version integer NOT NULL DEFAULT 1"
            ),
        )
    )
    op.execute("""
    ALTER TABLE app_user
      ADD CONSTRAINT uq_app_user_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT fk_app_user_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      ADD CONSTRAINT ck_app_user_user_class CHECK (user_class IN ('staff', 'field', 'portal')),
      ADD CONSTRAINT ck_app_user_status CHECK (status IN ('invited', 'active', 'deactivated')),
      ADD CONSTRAINT ck_app_user_deactivated_at
        CHECK ((status = 'deactivated') = (deactivated_at IS NOT NULL)),
      ADD CONSTRAINT ck_app_user_email CHECK (email ~ '^[^@[:space:]]+@[^@[:space:]]+$'),
      ADD CONSTRAINT ck_app_user_display_name
        CHECK (btrim(display_name) <> '' AND length(display_name) <= 200),
      ADD CONSTRAINT ck_app_user_idp_alias CHECK (idp_alias <> ''),
      ADD CONSTRAINT ck_app_user_external_id CHECK (external_id <> ''),
      ADD CONSTRAINT ck_app_user_sync_version CHECK (sync_version >= 1);

    CREATE UNIQUE INDEX uq_app_user_tenant_id_email
      ON app_user (tenant_id, email) WHERE deleted_at IS NULL;
    -- Not partial on deleted_at: a soft-deleted user's Keycloak account can never be re-provisioned
    -- as a fresh row; it must be restored on purpose.
    CREATE UNIQUE INDEX uq_app_user_tenant_id_keycloak_user_id
      ON app_user (tenant_id, keycloak_user_id) WHERE keycloak_user_id IS NOT NULL;
    CREATE INDEX ix_app_user_tenant_id_status ON app_user (tenant_id, status)
      WHERE deleted_at IS NULL;
    CREATE INDEX ix_app_user_tenant_id_organisation_id ON app_user (tenant_id, organisation_id);
    """)
    op.execute(
        render_template(
            "tenant_table",
            table="tenant_membership",
            columns=(
                "user_id uuid NOT NULL, organisation_id uuid NULL, "
                "membership_type text NOT NULL, valid_from date NOT NULL DEFAULT current_date, "
                "valid_to date NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE tenant_membership
      ADD CONSTRAINT fk_tenant_membership_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      -- (user_id, tenant_id): a membership can never point at another tenant's user.
      ADD CONSTRAINT fk_tenant_membership_user_id_tenant_id_app_user
        FOREIGN KEY (user_id, tenant_id) REFERENCES app_user (id, tenant_id),
      ADD CONSTRAINT ck_tenant_membership_membership_type
        CHECK (membership_type IN ('member', 'client', 'subcontractor', 'guest')),
      ADD CONSTRAINT ck_tenant_membership_valid_to
        CHECK (valid_to IS NULL OR valid_to >= valid_from);

    CREATE UNIQUE INDEX uq_tenant_membership_tenant_id_user_id_organisation_id
      ON tenant_membership (tenant_id, user_id, organisation_id) NULLS NOT DISTINCT
      WHERE deleted_at IS NULL;
    CREATE INDEX ix_tenant_membership_tenant_id_user_id ON tenant_membership (tenant_id, user_id);
    """)
    op.execute("""
    CREATE TABLE auth_event (
      id uuid NOT NULL,
      tenant_id uuid NOT NULL,
      user_id uuid NULL,
      event_type text NOT NULL,
      ip inet NULL,
      user_agent text NULL,
      detail jsonb NOT NULL DEFAULT '{}'::jsonb,
      occurred_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT pk_auth_event PRIMARY KEY (id),
      CONSTRAINT fk_auth_event_tenant_id_tenants FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      -- (user_id, tenant_id): an event can never point at another tenant's user (MATCH SIMPLE:
      -- a NULL user_id is not checked).
      CONSTRAINT fk_auth_event_user_id_tenant_id_app_user
        FOREIGN KEY (user_id, tenant_id) REFERENCES app_user (id, tenant_id),
      CONSTRAINT ck_auth_event_event_type CHECK (event_type ~ '^[a-z][a-z0-9_]*(\\.[a-z0-9_]+)+$'),
      CONSTRAINT ck_auth_event_user_agent CHECK (length(user_agent) <= 512),
      CONSTRAINT ck_auth_event_detail CHECK (jsonb_typeof(detail) = 'object')
    );

    CREATE INDEX ix_auth_event_tenant_id_user_id_occurred_at
      ON auth_event (tenant_id, user_id, occurred_at DESC);
    CREATE INDEX ix_auth_event_tenant_id_event_type_occurred_at
      ON auth_event (tenant_id, event_type, occurred_at);

    ALTER TABLE auth_event ENABLE ROW LEVEL SECURITY;
    ALTER TABLE auth_event FORCE ROW LEVEL SECURITY;

    CREATE POLICY tenant_isolation ON auth_event
      FOR ALL
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

    -- Append-only: no runtime role may UPDATE or DELETE an event.
    REVOKE ALL ON TABLE auth_event FROM PUBLIC;
    GRANT SELECT, INSERT ON auth_event TO aip_app;
    GRANT SELECT ON auth_event TO aip_readonly;
    """)
    op.execute("""
    ALTER TABLE login_directory
      DROP CONSTRAINT ck_login_directory_kind,
      ADD CONSTRAINT ck_login_directory_kind
        CHECK (kind IN ('email_domain', 'tenant_slug', 'email')),
      -- A local account's email names a tenant, never an IdP.
      ADD CONSTRAINT ck_login_directory_email_no_idp CHECK (kind <> 'email' OR idp_alias IS NULL);
    """)
    # contract: 202610091851 - SECURITY DEFINER on purpose (ADR 0005): aip_app has no privilege
    # on login_directory. Owned by aip_owner, fixed search_path, EXECUTE to aip_app only. It
    # writes only for the tenant bound to the current transaction and only an email held by a live
    # local app_user of that tenant (FORCE RLS binds the owner to app.tenant_id as well).
    op.execute("""
    CREATE FUNCTION identity_register_email(p_email citext, p_tenant uuid)
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
    REVOKE ALL ON FUNCTION identity_register_email(citext, uuid) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION identity_register_email(citext, uuid) TO aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
