"""access_permission_catalogue

ACCESS-01 (ADR 0020): the global permission catalogue and the per-tenant access version.

- ``permission``: global reference data mirrored from the module manifests (code PK, no
  ``tenant_id``, no RLS). ``aip_app`` and ``aip_readonly`` may only SELECT it. Writes go only
  through ``access_sync_permissions(p_catalogue jsonb)`` (SECURITY DEFINER), which the API calls
  at startup: it upserts every declared code and sets ``deprecated_at`` on codes of the same
  modules that are no longer declared. Rows are never deleted, so role grants (ACCESS-02) keep
  pointing at a real code. During a rolling deploy an older replica that restarts can deprecate a
  code a newer one added until the next newer start; ``deprecated_at`` is informational and must
  never hide a code a role still grants.
- ``access_settings``: one live row per tenant (tenant table template: FORCE RLS, soft delete)
  holding ``access_version``. Every role edit, reset, project override and assignment change
  bumps it in the same transaction (ACCESS-02), and any cross-request grant cache is keyed by it
  (ACCESS-04), so a change applies on the next request without signing out. A tenant with no row
  is at version 1. The version never goes down (trigger; ``aip_app`` has no DELETE).

Revision ID: 202610120445
Revises: 202610091851
Create Date: 2026-10-12 04:45:17.292557+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610120445"
down_revision: str | None = "202610091851"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
    CREATE TABLE permission (
      code text NOT NULL,
      module_id text NOT NULL,
      description text NOT NULL,
      is_privileged boolean NOT NULL DEFAULT false,
      deprecated_at timestamptz NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT pk_permission PRIMARY KEY (code),
      CONSTRAINT ck_permission_code
        CHECK (code ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,2}$'),
      CONSTRAINT ck_permission_module_id CHECK (module_id ~ '^[a-z][a-z0-9_]*$'),
      CONSTRAINT ck_permission_description
        CHECK (btrim(description) <> '' AND length(description) <= 500)
    );
    CREATE INDEX ix_permission_module_id ON permission (module_id);
    REVOKE ALL ON TABLE permission FROM PUBLIC;
    GRANT SELECT ON permission TO aip_app, aip_readonly;
    """)
    # contract: 202610120445 - SECURITY DEFINER on purpose (ACCESS-01): the only write path to the
    # global catalogue for aip_app, owned by aip_owner, fixed search_path, parameterised SQL only.
    # Guards, because the table is global (any aip_app session can call it): an empty or
    # non-array catalogue is refused; a privileged code is never downgraded (that needs a
    # migration); only codes of the modules in the payload are deprecated; rows are never deleted.
    op.execute("""
    CREATE FUNCTION access_sync_permissions(p_catalogue jsonb)
    RETURNS void
    LANGUAGE plpgsql
    VOLATILE
    SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $fn$
    DECLARE
      v_modules text[];
    BEGIN
      IF p_catalogue IS NULL OR jsonb_typeof(p_catalogue) <> 'array'
         OR jsonb_array_length(p_catalogue) = 0 THEN
        RAISE EXCEPTION 'access_sync_permissions: empty or invalid catalogue'
          USING ERRCODE = '22023';
      END IF;
      PERFORM pg_advisory_xact_lock(hashtext('access_sync_permissions'));
      IF EXISTS (
        SELECT 1
        FROM jsonb_to_recordset(p_catalogue) AS e(code text, is_privileged boolean)
        JOIN public.permission AS p ON p.code = e.code
        WHERE p.is_privileged AND NOT coalesce(e.is_privileged, false)
      ) THEN
        RAISE EXCEPTION 'access_sync_permissions: a privileged permission cannot be downgraded'
          USING ERRCODE = '42501';
      END IF;
      SELECT array_agg(DISTINCT e.module_id) INTO v_modules
      FROM jsonb_to_recordset(p_catalogue) AS e(module_id text);

      INSERT INTO public.permission AS p (code, module_id, description, is_privileged)
      SELECT e.code, e.module_id, e.description, coalesce(e.is_privileged, false)
      FROM jsonb_to_recordset(p_catalogue)
        AS e(code text, module_id text, description text, is_privileged boolean)
      ON CONFLICT (code) DO UPDATE
        SET module_id = excluded.module_id,
            description = excluded.description,
            is_privileged = excluded.is_privileged,
            deprecated_at = NULL,
            updated_at = now()
        WHERE (p.module_id, p.description, p.is_privileged, p.deprecated_at)
          IS DISTINCT FROM (excluded.module_id, excluded.description, excluded.is_privileged, NULL);

      UPDATE public.permission AS p
        SET deprecated_at = now(), updated_at = now()
        WHERE p.deprecated_at IS NULL
          AND p.module_id = ANY (v_modules)
          AND NOT EXISTS (
            SELECT 1 FROM jsonb_to_recordset(p_catalogue) AS e(code text) WHERE e.code = p.code
          );
    END;
    $fn$;
    REVOKE ALL ON FUNCTION access_sync_permissions(jsonb) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION access_sync_permissions(jsonb) TO aip_app;
    """)
    op.execute(
        render_template(
            "tenant_table",
            table="access_settings",
            columns="access_version bigint NOT NULL DEFAULT 1",
        )
    )
    op.execute("""
    ALTER TABLE access_settings
      ADD CONSTRAINT fk_access_settings_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      ADD CONSTRAINT ck_access_settings_access_version CHECK (access_version >= 1);
    CREATE UNIQUE INDEX uq_access_settings_tenant_id
      ON access_settings (tenant_id) WHERE deleted_at IS NULL;
    """)
    # The version only ever goes up (ACCESS-04 caches grants by it, so a reused number could serve
    # stale grants): no DELETE for aip_app, and a trigger refuses lowering it, soft-deleting the
    # row or moving it to another tenant.
    op.execute("""
    REVOKE DELETE ON access_settings FROM aip_app;
    CREATE FUNCTION access_settings_version_guard()
    RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, public
    AS $fn$
    BEGIN
      IF NEW.access_version <= OLD.access_version THEN
        RAISE EXCEPTION 'access_version must increase' USING ERRCODE = '23514';
      END IF;
      IF NEW.deleted_at IS NOT NULL OR NEW.id <> OLD.id OR NEW.tenant_id <> OLD.tenant_id THEN
        RAISE EXCEPTION 'access_settings rows are never deleted or moved' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END;
    $fn$;
    CREATE TRIGGER trg_access_settings_version_guard
      BEFORE UPDATE ON access_settings
      FOR EACH ROW EXECUTE FUNCTION access_settings_version_guard();
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
