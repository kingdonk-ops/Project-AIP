"""terms_tables

TERMS-01: the terminology dictionary tables (``docs/blueprint/modules/terms/data-model.md``):
``term_key``, ``term_pack``, ``term_pack_version``, ``term_override``, ``glossary_entry``,
``term_alias`` and ``locale_settings``, each from ``db/templates/tenant_table.sql.tpl``.

Platform rows (the en-AU defaults, built-in packs) carry the reserved platform tenant, the nil
UUID (ADR 0028). It is not a row in ``tenants``, so there is no FK. Each table swaps the template's
``tenant_isolation`` policy for two permissive policies:

- ``tenant_write`` (FOR ALL, the one the schema guard asserts): the row's tenant is the bound
  tenant, and a platform row only when the role is ``aip_owner``. So ``aip_app`` can never write a
  platform row, even with ``app.tenant_id`` set to the nil UUID by hand.
- ``platform_read`` (FOR SELECT): platform rows are readable by every tenant.

Together a tenant reads its own rows plus platform rows and writes only its own. An unset
``app.tenant_id`` still fails closed for writes; reads then see platform rows only. Deletes are
soft: ``aip_app`` has no DELETE anywhere. It has no UPDATE on ``term_pack_version`` (immutable
versions; rollback activates an older one), and only SELECT on ``term_key``: the key catalogue is
platform data written by the deploy loader, and tenants override keys through ``term_override``.

Cross-module references (``users``, ``projects``, contacts companies) are plain uuid columns:
modules may not reach into each other's tables. Within terms, pack references include
``tenant_id`` so a pack can never point at another tenant's version.

Revision ID: 202610141000
Revises: 202610131600
Create Date: 2026-10-14 10:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610141000"
down_revision: str | None = "202610131600"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- term_key: the catalogue of dictionary keys with their platform default ---------------
    op.execute(
        render_template(
            "tenant_table",
            table="term_key",
            columns=(
                "key text NOT NULL, module_id text NOT NULL, "
                "default_locale text NOT NULL, "
                "default_text text NOT NULL, description text NULL"
            ),
        )
    )
    op.execute(
        """
    ALTER TABLE term_key ALTER COLUMN default_locale SET DEFAULT 'en-AU';
    ALTER TABLE term_key
      ADD CONSTRAINT ck_term_key_key CHECK (key ~ '^[a-z][a-z0-9_]*(\\.[A-Za-z0-9_]+)+$'),
      ADD CONSTRAINT ck_term_key_module_id CHECK (module_id ~ '^[a-z][a-z0-9_]*$'),
      ADD CONSTRAINT ck_term_key_default_text CHECK (default_text <> '');

    -- Plain (not partial) so the loader's ON CONFLICT (key) can infer it.
    CREATE UNIQUE INDEX uq_term_key_key ON term_key (key);
    CREATE INDEX ix_term_key_module_id ON term_key (module_id);

    DROP POLICY tenant_isolation ON term_key;

    CREATE POLICY tenant_write ON term_key
      FOR ALL
      USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        AND (tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid
             OR current_user = 'aip_owner')
      )
      WITH CHECK (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        AND (tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid
             OR current_user = 'aip_owner')
      );

    CREATE POLICY platform_read ON term_key
      FOR SELECT
      USING (tenant_id = '00000000-0000-0000-0000-000000000000'::uuid);

    REVOKE DELETE ON term_key FROM aip_app;

    -- The key catalogue is platform-only: tenants override through term_override. With INSERT a
    -- tenant could take a key name before a release ships it (key is globally unique), and the
    -- deploy loader's upsert would then fail on a row it cannot update.
    REVOKE INSERT, UPDATE ON term_key FROM aip_app;
    """
    )

    # --- term_pack and term_pack_version: market or client packs, immutable versions ---------
    op.execute(
        render_template(
            "tenant_table",
            table="term_pack",
            columns="code text NOT NULL, name text NOT NULL, active_version_id uuid NULL",
        )
    )
    op.execute(
        render_template(
            "tenant_table",
            table="term_pack_version",
            columns=(
                "pack_id uuid NOT NULL, version integer NOT NULL, contents jsonb NOT NULL, "
                "contents_sha256 text NOT NULL, change_summary jsonb NULL, "
                "created_by uuid NULL"
            ),
        )
    )
    op.execute(
        """
    ALTER TABLE term_pack
      ADD CONSTRAINT uq_term_pack_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT ck_term_pack_code CHECK (code ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
      ADD CONSTRAINT ck_term_pack_name CHECK (name <> '');
    CREATE UNIQUE INDEX uq_term_pack_tenant_id_code ON term_pack (tenant_id, code);

    ALTER TABLE term_pack_version
      ADD CONSTRAINT uq_term_pack_version_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT ck_term_pack_version_version CHECK (version >= 1),
      ADD CONSTRAINT ck_term_pack_version_contents CHECK (jsonb_typeof(contents) = 'object'),
      ADD CONSTRAINT ck_term_pack_version_sha256 CHECK (contents_sha256 ~ '^[0-9a-f]{64}$'),
      ADD CONSTRAINT fk_term_pack_version_pack_id_tenant_id_term_pack
        FOREIGN KEY (pack_id, tenant_id) REFERENCES term_pack (id, tenant_id);
    CREATE UNIQUE INDEX uq_term_pack_version_pack_id_version
      ON term_pack_version (pack_id, version);

    ALTER TABLE term_pack
      ADD CONSTRAINT fk_term_pack_active_version_id_tenant_id_term_pack_version
        FOREIGN KEY (active_version_id, tenant_id)
        REFERENCES term_pack_version (id, tenant_id);

    DROP POLICY tenant_isolation ON term_pack;

    CREATE POLICY tenant_write ON term_pack
      FOR ALL
      USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        AND (tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid
             OR current_user = 'aip_owner')
      )
      WITH CHECK (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        AND (tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid
             OR current_user = 'aip_owner')
      );

    CREATE POLICY platform_read ON term_pack
      FOR SELECT
      USING (tenant_id = '00000000-0000-0000-0000-000000000000'::uuid);

    REVOKE DELETE ON term_pack FROM aip_app;
    DROP POLICY tenant_isolation ON term_pack_version;

    CREATE POLICY tenant_write ON term_pack_version
      FOR ALL
      USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        AND (tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid
             OR current_user = 'aip_owner')
      )
      WITH CHECK (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        AND (tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid
             OR current_user = 'aip_owner')
      );

    CREATE POLICY platform_read ON term_pack_version
      FOR SELECT
      USING (tenant_id = '00000000-0000-0000-0000-000000000000'::uuid);

    REVOKE DELETE ON term_pack_version FROM aip_app;
    -- Append-only: a version is never edited; rollback activates an older one.
    REVOKE UPDATE ON term_pack_version FROM aip_app;
    """
    )

    # --- term_override: tenant, client or project override of one key ----------------------
    op.execute(
        render_template(
            "tenant_table",
            table="term_override",
            columns=(
                "level text NOT NULL, client_org_id uuid NULL, project_id uuid NULL, "
                "key text NOT NULL, locale text NOT NULL, text text NOT NULL, "
                "sync_version integer NOT NULL DEFAULT 1, created_by uuid NULL"
            ),
        )
    )
    op.execute(
        """
    ALTER TABLE term_override
      ADD CONSTRAINT ck_term_override_level CHECK (
        (level = 'tenant' AND client_org_id IS NULL AND project_id IS NULL)
        OR (level = 'client' AND client_org_id IS NOT NULL AND project_id IS NULL)
        OR (level = 'project' AND project_id IS NOT NULL AND client_org_id IS NULL)
      ),
      ADD CONSTRAINT ck_term_override_text CHECK (text <> ''),
      ADD CONSTRAINT ck_term_override_sync_version CHECK (sync_version >= 1),
      -- Only a key the catalogue defines can be overridden (the FK check bypasses RLS).
      ADD CONSTRAINT fk_term_override_key_term_key FOREIGN KEY (key) REFERENCES term_key (key);

    -- The nil UUID stands in for "no scope" at tenant level: NULLs are distinct in a unique
    -- index, so without it a tenant could hold two live tenant-level overrides of one key.
    CREATE UNIQUE INDEX uq_term_override_scope_key_locale ON term_override (
      tenant_id, level,
      coalesce(client_org_id, project_id, '00000000-0000-0000-0000-000000000000'::uuid),
      key, locale
    ) WHERE deleted_at IS NULL;
    CREATE INDEX ix_term_override_tenant_id_key ON term_override (tenant_id, key);

    DROP POLICY tenant_isolation ON term_override;

    CREATE POLICY tenant_write ON term_override
      FOR ALL
      USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        AND (tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid
             OR current_user = 'aip_owner')
      )
      WITH CHECK (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        AND (tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid
             OR current_user = 'aip_owner')
      );

    CREATE POLICY platform_read ON term_override
      FOR SELECT
      USING (tenant_id = '00000000-0000-0000-0000-000000000000'::uuid);

    REVOKE DELETE ON term_override FROM aip_app;
    """
    )

    # --- glossary_entry: standards and abbreviations shown as tooltips ----------------------
    op.execute(
        render_template(
            "tenant_table",
            table="glossary_entry",
            columns=(
                "term text NOT NULL, abbreviation text NULL, definition text NOT NULL, "
                "neutral_concept_code text NULL, locale text NOT NULL"
            ),
        )
    )
    op.execute(
        """
    ALTER TABLE glossary_entry
      ADD CONSTRAINT ck_glossary_entry_term CHECK (term <> '');
    CREATE INDEX ix_glossary_entry_tenant_id_abbreviation
      ON glossary_entry (tenant_id, abbreviation);
    CREATE INDEX ix_glossary_entry_tenant_id_neutral_concept_code
      ON glossary_entry (tenant_id, neutral_concept_code);

    DROP POLICY tenant_isolation ON glossary_entry;

    CREATE POLICY tenant_write ON glossary_entry
      FOR ALL
      USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        AND (tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid
             OR current_user = 'aip_owner')
      )
      WITH CHECK (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        AND (tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid
             OR current_user = 'aip_owner')
      );

    CREATE POLICY platform_read ON glossary_entry
      FOR SELECT
      USING (tenant_id = '00000000-0000-0000-0000-000000000000'::uuid);

    REVOKE DELETE ON glossary_entry FROM aip_app;
    """
    )

    # --- term_alias: alias to neutral code, for search and import header mapping ------------
    op.execute(
        render_template(
            "tenant_table",
            table="term_alias",
            columns=(
                "alias text NOT NULL, target_type text NOT NULL, target_code text NOT NULL, "
                "locale text NOT NULL"
            ),
        )
    )
    op.execute(
        """
    ALTER TABLE term_alias
      ADD CONSTRAINT ck_term_alias_alias CHECK (alias <> '' AND alias = lower(alias)),
      ADD CONSTRAINT ck_term_alias_target_type
        CHECK (target_type IN ('entity_type', 'field', 'status'));
    CREATE UNIQUE INDEX uq_term_alias_tenant_id_alias_target_type_locale
      ON term_alias (tenant_id, alias, target_type, locale) WHERE deleted_at IS NULL;
    CREATE INDEX ix_term_alias_alias_trgm ON term_alias USING gin (alias gin_trgm_ops);

    DROP POLICY tenant_isolation ON term_alias;

    CREATE POLICY tenant_write ON term_alias
      FOR ALL
      USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        AND (tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid
             OR current_user = 'aip_owner')
      )
      WITH CHECK (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        AND (tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid
             OR current_user = 'aip_owner')
      );

    CREATE POLICY platform_read ON term_alias
      FOR SELECT
      USING (tenant_id = '00000000-0000-0000-0000-000000000000'::uuid);

    REVOKE DELETE ON term_alias FROM aip_app;
    """
    )

    # --- locale_settings: locale, formats and display units per tenant or project -----------
    op.execute(
        render_template(
            "tenant_table",
            table="locale_settings",
            columns=(
                "project_id uuid NULL, locale text NOT NULL, "
                "date_format text NULL, number_format text NULL, "
                "unit_system text NOT NULL, "
                "unit_overrides jsonb NOT NULL, timezone text NULL"
            ),
        )
    )
    op.execute(
        """
    ALTER TABLE locale_settings
      ALTER COLUMN locale SET DEFAULT 'en-AU',
      ALTER COLUMN unit_system SET DEFAULT 'metric',
      ALTER COLUMN unit_overrides SET DEFAULT '{}'::jsonb;
    ALTER TABLE locale_settings
      ADD CONSTRAINT ck_locale_settings_unit_system
        CHECK (unit_system IN ('metric', 'imperial')),
      ADD CONSTRAINT ck_locale_settings_unit_overrides
        CHECK (jsonb_typeof(unit_overrides) = 'object');
    CREATE UNIQUE INDEX uq_locale_settings_tenant_id_project_id ON locale_settings (
      tenant_id, coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) WHERE deleted_at IS NULL;

    DROP POLICY tenant_isolation ON locale_settings;

    CREATE POLICY tenant_write ON locale_settings
      FOR ALL
      USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        AND (tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid
             OR current_user = 'aip_owner')
      )
      WITH CHECK (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        AND (tenant_id <> '00000000-0000-0000-0000-000000000000'::uuid
             OR current_user = 'aip_owner')
      );

    CREATE POLICY platform_read ON locale_settings
      FOR SELECT
      USING (tenant_id = '00000000-0000-0000-0000-000000000000'::uuid);

    REVOKE DELETE ON locale_settings FROM aip_app;
    """
    )


def downgrade() -> None:
    raise NotImplementedError("forward-only")
