"""access_default_role_template

ACCESS-09 (ADR 0042): the operator's default role template.

- ``default_role_level``: one row per access-matrix cell (module x system role) the operator has
  moved away from the shipped ``MATRIX`` in ``aip.modules.access.roles.default_roles``. No row
  means the shipped level. Global platform data (no ``tenant_id``, no RLS), like ``permission``;
  it holds no tenant data. On the schema-guard allow-list. ``aip_app`` and ``aip_readonly`` may
  only SELECT it (every tenant's ``seed_default_roles`` reads it).
- ``default_role_level_change``: the append-only history of every change (who, when, cell, level
  before and after, reason). ``aip_app`` and ``aip_readonly`` may only SELECT it.
- ``access_set_default_role_level(...)``: the only write path to both tables (SECURITY DEFINER,
  EXECUTE to ``aip_app`` only). It moves one cell and writes its history row in the same call, so
  no runtime role can change the template without a history row, nor edit or forge history. The
  ``platform.roles.manage``-gated operator API calls it; a reset (the shipped level) deletes the row.

The CHECKs repeat the service guardrails so a hand-written row cannot break them: the 11 system
role codes, the six levels, Client Reviewer only ``none``/``view``/``approve`` (sign-off only,
ADR 0027) and Tenant Admin always ``admin`` on ``access`` (no tenant lockout, ADR 0020).

Revision ID: 202611021000
Revises: 202611011600
Create Date: 2026-11-02 10:00:00+00:00
"""

from alembic import op

revision: str = "202611021000"
down_revision: str | None = "202611011600"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE default_role_level (
      module_id text NOT NULL,
      role_code text NOT NULL,
      level text NOT NULL,
      updated_by uuid NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT pk_default_role_level PRIMARY KEY (module_id, role_code),
      CONSTRAINT ck_default_role_level_module_id CHECK (module_id ~ '^[a-z][a-z0-9_]*$'),
      CONSTRAINT ck_default_role_level_role_code CHECK (role_code IN (
        'tenant_admin', 'project_manager', 'qaqc_manager', 'hse_officer', 'supervisor',
        'inspector', 'field_worker', 'document_controller', 'client_reviewer', 'subcontractor',
        'auditor'
      )),
      CONSTRAINT ck_default_role_level_level CHECK (
        level IN ('none', 'view', 'create', 'edit', 'approve', 'admin')
      ),
      CONSTRAINT ck_default_role_level_sign_off_only CHECK (
        role_code <> 'client_reviewer' OR level IN ('none', 'view', 'approve')
      ),
      CONSTRAINT ck_default_role_level_admin_keeps_access CHECK (
        NOT (role_code = 'tenant_admin' AND module_id = 'access') OR level = 'admin'
      )
    );
    REVOKE ALL ON TABLE default_role_level FROM PUBLIC;
    GRANT SELECT ON default_role_level TO aip_app, aip_readonly;

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
      CONSTRAINT ck_default_role_level_change_role_code CHECK (role_code IN (
        'tenant_admin', 'project_manager', 'qaqc_manager', 'hse_officer', 'supervisor',
        'inspector', 'field_worker', 'document_controller', 'client_reviewer', 'subcontractor',
        'auditor'
      )),
      CONSTRAINT ck_default_role_level_change_level_before CHECK (
        level_before IN ('none', 'view', 'create', 'edit', 'approve', 'admin')
      ),
      CONSTRAINT ck_default_role_level_change_level_after CHECK (
        level_after IN ('none', 'view', 'create', 'edit', 'approve', 'admin')
      ),
      CONSTRAINT ck_default_role_level_change_changed CHECK (level_before <> level_after),
      CONSTRAINT ck_default_role_level_change_reason CHECK (btrim(reason) <> '')
    );
    CREATE INDEX ix_default_role_level_change_role_changed_at
      ON default_role_level_change (role_code, changed_at);
    REVOKE ALL ON TABLE default_role_level_change FROM PUBLIC;
    GRANT SELECT ON default_role_level_change TO aip_app, aip_readonly;
    """)
    # contract: 202611021000 - SECURITY DEFINER on purpose (ACCESS-09, ADR 0042): the only write
    # path to the global default role template for aip_app, owned by aip_owner, fixed search_path,
    # parameterised SQL only. It sets one cell and appends its history row in the same call, so a
    # change can never skip the audit and history can never be edited. The table CHECKs still
    # refuse a bad role, level, Client Reviewer level or Tenant Admin access level. The caller
    # passes the shipped level (MATRIX lives in code): the shipped level deletes the row, and the
    # history's level_before is the stored row's level, or the shipped level when there is none.
    op.execute("""
    CREATE FUNCTION access_set_default_role_level(
      p_module text, p_role text, p_level text, p_shipped text, p_actor uuid, p_reason text
    )
    RETURNS SETOF default_role_level_change
    LANGUAGE plpgsql
    VOLATILE
    SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $fn$
    DECLARE
      v_current text;
      v_before text;
    BEGIN
      IF p_shipped IS NULL
         OR p_shipped NOT IN ('none', 'view', 'create', 'edit', 'approve', 'admin') THEN
        RAISE EXCEPTION 'access_set_default_role_level: invalid shipped level'
          USING ERRCODE = '22023';
      END IF;
      IF p_reason IS NULL OR btrim(p_reason) = '' THEN
        RAISE EXCEPTION 'access_set_default_role_level: a reason is required'
          USING ERRCODE = '22023';
      END IF;
      PERFORM pg_advisory_xact_lock(hashtextextended('access.default_role_template', 0));
      SELECT d.level INTO v_current
        FROM public.default_role_level AS d
        WHERE d.module_id = p_module AND d.role_code = p_role
        FOR UPDATE;
      v_before := COALESCE(v_current, p_shipped);
      IF p_level = p_shipped THEN
        DELETE FROM public.default_role_level AS d
          WHERE d.module_id = p_module AND d.role_code = p_role;
      ELSE
        INSERT INTO public.default_role_level (module_id, role_code, level, updated_by)
          VALUES (p_module, p_role, p_level, p_actor)
          ON CONFLICT (module_id, role_code) DO UPDATE
            SET level = excluded.level, updated_by = excluded.updated_by, updated_at = now();
      END IF;
      IF v_before IS DISTINCT FROM p_level THEN
        RETURN QUERY
          INSERT INTO public.default_role_level_change
            (id, module_id, role_code, level_before, level_after, changed_by, reason)
          VALUES (gen_random_uuid(), p_module, p_role, v_before, p_level, p_actor, p_reason)
          RETURNING *;
      END IF;
    END;
    $fn$;
    REVOKE ALL ON FUNCTION access_set_default_role_level(text, text, text, text, uuid, text)
      FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION access_set_default_role_level(text, text, text, text, uuid, text)
      TO aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
