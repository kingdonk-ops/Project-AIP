"""portal_users_grants

PORTAL-01 (ADR 0036 owner answers): external portal users and their per-project grants, both from
``db/templates/tenant_table.sql.tpl`` (uuid PK, tenant_id, timestamps, soft delete, FORCE RLS with
the fail-closed NULLIF policy). Deletes are soft: ``aip_app`` keeps only the template's SELECT,
INSERT and UPDATE.

- ``portal_users`` is 1:1 with identity's ``app_user`` (``user_id``; no cross-module FK, checked
  through ``aip.modules.identity.api.get_user``): one live row per user and tenant, a company name
  of 1 to 200 characters, status ``invited``/``active``/``suspended`` and a 1 to 500 character
  suspension reason. ``(id, tenant_id)`` is unique so grants reference it within one tenant.
- ``portal_grants``: a project, an optional asset subtree root and the actions (1 to 4 of
  ``view``/``sign_off``/``witness``/``download``, always with ``view``), the project's access period
  (``access_days`` 1 to 400) and its ``expires_at``. A revoked grant carries both ``revoked_at``
  and a ``revoked_reason`` (``manual``/``project_closed``/``user_suspended``). One live grant per
  user, project and subtree (a partial unique index, the null subtree coalesced to the nil uuid);
  the ``(tenant_id, expires_at)`` index serves PORTAL-08's reminder job.
- ``role_permission`` may never hold an external-only ``portal.record.*`` / ``portal.report.*``
  code (``ck_role_permission_not_external_only``): only portal grants give those.

Revision ID: 202610291100
Revises: 202610291000
Create Date: 2026-10-28 16:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610291100"
down_revision: str | None = "202610291000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="portal_users",
            columns=(
                "user_id uuid NOT NULL, company_name text NOT NULL, organisation_id uuid NULL, "
                "status text NOT NULL, invited_by uuid NOT NULL, "
                "first_signed_in_at timestamptz NULL, suspended_at timestamptz NULL, "
                "suspended_reason text NULL, sync_version integer NOT NULL DEFAULT 1"
            ),
        )
    )
    op.execute(
        render_template(
            "tenant_table",
            table="portal_grants",
            columns=(
                "portal_user_id uuid NOT NULL, project_id uuid NOT NULL, asset_id uuid NULL, "
                "actions text[] NOT NULL, access_days integer NOT NULL, "
                "expires_at timestamptz NOT NULL, renewed_at timestamptz NULL, "
                "renewed_by uuid NULL, revoked_at timestamptz NULL, revoked_by uuid NULL, "
                "revoked_reason text NULL, created_by uuid NOT NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE portal_users ALTER COLUMN status SET DEFAULT 'invited';
    ALTER TABLE portal_users
      ADD CONSTRAINT uq_portal_users_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT ck_portal_users_company_name
        CHECK (btrim(company_name) <> '' AND length(company_name) <= 200),
      ADD CONSTRAINT ck_portal_users_status CHECK (status IN ('invited', 'active', 'suspended')),
      ADD CONSTRAINT ck_portal_users_suspended_reason
        CHECK (suspended_reason IS NULL
               OR (btrim(suspended_reason) <> '' AND length(suspended_reason) <= 500)),
      ADD CONSTRAINT ck_portal_users_sync_version CHECK (sync_version >= 1);

    CREATE UNIQUE INDEX uq_portal_users_tenant_id_user_id
      ON portal_users (tenant_id, user_id) WHERE deleted_at IS NULL;
    CREATE INDEX ix_portal_users_tenant_id_status ON portal_users (tenant_id, status);

    ALTER TABLE portal_grants
      -- (portal_user_id, tenant_id) so a grant can never point at another tenant's portal user.
      ADD CONSTRAINT fk_portal_grants_portal_user
        FOREIGN KEY (portal_user_id, tenant_id) REFERENCES portal_users (id, tenant_id),
      ADD CONSTRAINT ck_portal_grants_actions
        CHECK (cardinality(actions) BETWEEN 1 AND 4
               AND actions <@ ARRAY['view', 'sign_off', 'witness', 'download']::text[]
               AND 'view' = ANY (actions)),
      ADD CONSTRAINT ck_portal_grants_access_days CHECK (access_days BETWEEN 1 AND 400),
      ADD CONSTRAINT ck_portal_grants_revoked_reason
        CHECK (revoked_reason IN ('manual', 'project_closed', 'user_suspended')),
      ADD CONSTRAINT ck_portal_grants_revoked_shape
        CHECK ((revoked_at IS NULL) = (revoked_reason IS NULL));

    CREATE INDEX ix_portal_grants_tenant_id_portal_user_id_live
      ON portal_grants (tenant_id, portal_user_id)
      WHERE revoked_at IS NULL AND deleted_at IS NULL;
    CREATE INDEX ix_portal_grants_tenant_id_project_id ON portal_grants (tenant_id, project_id);
    CREATE INDEX ix_portal_grants_tenant_id_expires_at_live
      ON portal_grants (tenant_id, expires_at)
      WHERE revoked_at IS NULL AND deleted_at IS NULL;
    -- One live grant per user, project and subtree (a project-wide grant has no asset).
    CREATE UNIQUE INDEX uq_portal_grants_live_user_project_asset
      ON portal_grants (tenant_id, portal_user_id, project_id,
                        coalesce(asset_id, '00000000-0000-0000-0000-000000000000'::uuid))
      WHERE revoked_at IS NULL AND deleted_at IS NULL;
    """)

    # Defence in depth (PORTAL-01 review): no role may hold an external-only portal code,
    # whatever the write path (mirrors ck_role_permission_not_operator_only).
    op.execute(
        "ALTER TABLE role_permission ADD CONSTRAINT ck_role_permission_not_external_only"
        " CHECK (permission_code NOT LIKE 'portal.record.%'"
        " AND permission_code NOT LIKE 'portal.report.%');"
    )


def downgrade() -> None:
    raise NotImplementedError("forward-only")
