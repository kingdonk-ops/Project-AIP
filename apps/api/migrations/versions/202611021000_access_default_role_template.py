"""access_default_role_template

ACCESS-09 (ADR 0042): the operator's default role template.

- ``default_role_level``: one row per access-matrix cell (module x system role) the operator has
  moved away from the shipped ``MATRIX`` in ``aip.modules.access.roles.default_roles``. No row
  means the shipped level. Global platform data (no ``tenant_id``, no RLS), like ``permission``;
  it holds no tenant data. On the schema-guard allow-list. ``aip_app`` may SELECT, INSERT, UPDATE
  and DELETE it (the ``platform.roles.manage``-gated operator API; a reset deletes the row) and
  every tenant's ``seed_default_roles`` reads it; ``aip_readonly`` may SELECT.
- ``default_role_level_change``: the append-only history of every change (who, when, cell, level
  before and after, reason). ``aip_app`` may only SELECT and INSERT.

The CHECKs repeat the service guardrails so a hand-written row cannot break them: the 11 system
role codes, the six levels, Client Reviewer only ``none``/``view``/``approve`` (sign-off only,
ADR 0027) and Tenant Admin always ``admin`` on ``access`` (no tenant lockout, ADR 0020).

Revision ID: 202611021000
Revises: 202611011500
Create Date: 2026-11-02 10:00:00+00:00
"""

from alembic import op

revision: str = "202611021000"
down_revision: str | None = "202611011500"
branch_labels = None
depends_on = None

_ROLES = (
    "'tenant_admin', 'project_manager', 'qaqc_manager', 'hse_officer', 'supervisor', 'inspector',"
    " 'field_worker', 'document_controller', 'client_reviewer', 'subcontractor', 'auditor'"
)
_LEVELS = "'none', 'view', 'create', 'edit', 'approve', 'admin'"


def upgrade() -> None:
    op.execute(f"""
    CREATE TABLE default_role_level (
      module_id text NOT NULL,
      role_code text NOT NULL,
      level text NOT NULL,
      updated_by uuid NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT pk_default_role_level PRIMARY KEY (module_id, role_code),
      CONSTRAINT ck_default_role_level_module_id CHECK (module_id ~ '^[a-z][a-z0-9_]*$'),
      CONSTRAINT ck_default_role_level_role_code CHECK (role_code IN ({_ROLES})),
      CONSTRAINT ck_default_role_level_level CHECK (level IN ({_LEVELS})),
      CONSTRAINT ck_default_role_level_sign_off_only CHECK (
        role_code <> 'client_reviewer' OR level IN ('none', 'view', 'approve')
      ),
      CONSTRAINT ck_default_role_level_admin_keeps_access CHECK (
        NOT (role_code = 'tenant_admin' AND module_id = 'access') OR level = 'admin'
      )
    );
    REVOKE ALL ON TABLE default_role_level FROM PUBLIC;
    GRANT SELECT, INSERT, UPDATE, DELETE ON default_role_level TO aip_app;
    GRANT SELECT ON default_role_level TO aip_readonly;

    CREATE TABLE default_role_level_change (
      id uuid NOT NULL,
      module_id text NOT NULL,
      role_code text NOT NULL,
      level_before text NOT NULL,
      level_after text NOT NULL,
      changed_by uuid NULL,
      reason text NOT NULL,
      changed_at timestamptz NOT NULL DEFAULT now(),
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT pk_default_role_level_change PRIMARY KEY (id),
      CONSTRAINT ck_default_role_level_change_role_code CHECK (role_code IN ({_ROLES})),
      CONSTRAINT ck_default_role_level_change_level_before CHECK (level_before IN ({_LEVELS})),
      CONSTRAINT ck_default_role_level_change_level_after CHECK (level_after IN ({_LEVELS})),
      CONSTRAINT ck_default_role_level_change_changed CHECK (level_before <> level_after),
      CONSTRAINT ck_default_role_level_change_reason CHECK (btrim(reason) <> '')
    );
    CREATE INDEX ix_default_role_level_change_role_changed_at
      ON default_role_level_change (role_code, changed_at);
    REVOKE ALL ON TABLE default_role_level_change FROM PUBLIC;
    GRANT SELECT, INSERT ON default_role_level_change TO aip_app;
    GRANT SELECT ON default_role_level_change TO aip_readonly;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
