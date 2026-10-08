"""tenancy_tenants_regions

TENANCY-01 (ADR 0002, 0005, 0006): ``deployment_regions`` and ``tenants``.

- ``deployment_regions`` is a global reference table (code PK, no ``tenant_id``, no RLS; to be
  allow-listed by the TESTING-02 schema guard). Runtime roles may only read it. The three regions
  are reference data, seeded here; ``label_key`` is a terminology key, never a label.
- ``tenants`` is the tenant itself: ``id`` *is* the tenant id, so instead of a ``tenant_id``
  column its FORCE RLS policy is ``id = app.tenant_id`` (USING and WITH CHECK, fail closed when
  unset). ``aip_app`` and ``aip_readonly`` get SELECT only, so the app can read its own row and
  nothing else, and cannot create, change or delete a tenant. Provisioning (TENANCY-05) and the
  fixture seed (``python -m aip.modules.tenancy.seed``) write as the owner, which FORCE RLS also
  binds to one tenant per transaction. Slugs are unique for ever (also after soft delete), so a
  slug in ``login_directory`` can never be taken over by a later tenant.
- ``kms_key_ref`` stays NULL until TENANCY-05 provisioning creates the per-tenant key (ADR 0006).
- ``fk_login_directory_tenant_id_tenants``: the IDENTITY-01 login directory now points at real
  tenants. Postgres runs foreign-key checks without row security, so the global directory can
  reference RLS-protected rows. A database whose ``login_directory`` already holds dev rows for
  tenants that do not exist yet fails here: reset it, then run the tenancy seed before the
  identity seed. No fixture tenant is created by this revision.

Revision ID: 202610081122
Revises: 202610080600
Create Date: 2026-10-08 11:22:25.184659+00:00
"""

from alembic import op

revision: str = "202610081122"
down_revision: str | None = "202610080600"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE deployment_regions (
      code text NOT NULL,
      label_key text NOT NULL,
      in_country_only boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT pk_deployment_regions PRIMARY KEY (code),
      CONSTRAINT ck_deployment_regions_code CHECK (code ~ '^[a-z]{2}(-[a-z]+)+-[0-9]+$'),
      CONSTRAINT ck_deployment_regions_label_key CHECK (label_key ~ '^[a-z][a-z0-9_.]*$')
    );

    REVOKE ALL ON TABLE deployment_regions FROM PUBLIC;
    GRANT SELECT ON deployment_regions TO aip_app, aip_jobs, aip_readonly;

    INSERT INTO deployment_regions (code, label_key, in_country_only) VALUES
      ('ap-southeast-2', 'tenancy.region.ap_southeast_2', false),
      ('eu-west-2', 'tenancy.region.eu_west_2', false),
      ('ap-southeast-1', 'tenancy.region.ap_southeast_1', false);
    """)
    op.execute("""
    CREATE TABLE tenants (
      id uuid NOT NULL,
      name text NOT NULL,
      slug text NOT NULL,
      deployment_shape text NOT NULL DEFAULT 'pooled',
      region_code text NOT NULL,
      kms_key_ref text NULL,
      status text NOT NULL DEFAULT 'provisioning',
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      deleted_at timestamptz NULL,
      CONSTRAINT pk_tenants PRIMARY KEY (id),
      CONSTRAINT uq_tenants_slug UNIQUE (slug),
      CONSTRAINT fk_tenants_region_code_deployment_regions
        FOREIGN KEY (region_code) REFERENCES deployment_regions (code),
      CONSTRAINT ck_tenants_id CHECK (id <> '00000000-0000-0000-0000-000000000000'::uuid),
      CONSTRAINT ck_tenants_name CHECK (btrim(name) <> ''),
      CONSTRAINT ck_tenants_slug CHECK (slug ~ '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$'),
      CONSTRAINT ck_tenants_deployment_shape CHECK (deployment_shape IN ('pooled', 'siloed')),
      CONSTRAINT ck_tenants_status CHECK (
        status IN ('provisioning', 'active', 'suspended', 'offboarding', 'offboarded')
      ),
      CONSTRAINT ck_tenants_kms_key_ref CHECK (kms_key_ref <> '')
    );

    CREATE INDEX ix_tenants_status ON tenants (status);
    CREATE INDEX ix_tenants_region_code ON tenants (region_code);

    ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
    ALTER TABLE tenants FORCE ROW LEVEL SECURITY;

    -- The tenant row is visible only inside its own tenant context; unset fails closed.
    CREATE POLICY tenant_isolation ON tenants
      FOR ALL
      USING (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

    REVOKE ALL ON TABLE tenants FROM PUBLIC;
    GRANT SELECT ON tenants TO aip_app, aip_readonly;
    """)
    op.execute("""
    ALTER TABLE login_directory
      ADD CONSTRAINT fk_login_directory_tenant_id_tenants
      FOREIGN KEY (tenant_id) REFERENCES tenants (id);
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
