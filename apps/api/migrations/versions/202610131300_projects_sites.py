"""projects_sites

PROJECTS-01: the first real tenant register. ``sites`` (physical sites, with an optional GPS
point) and ``projects`` (scoped campaigns of work), both from ``db/templates/tenant_table.sql.tpl``
(uuid PK, tenant_id, timestamps, soft delete, FORCE RLS with the fail-closed NULLIF policy).

Deletes are soft, so ``aip_app`` loses the template's DELETE grant. Codes are unique per tenant
ignoring case among live rows. ``projects.site_id`` references ``sites`` together with
``tenant_id``, so a project can never point at another tenant's site. Plain lat/lng columns stand
in for PostGIS until a module needs spatial queries (ADR 0002).

Revision ID: 202610131300
Revises: 202610131000
Create Date: 2026-10-13 13:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610131300"
down_revision: str | None = "202610131000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="sites",
            columns=(
                "code text NOT NULL, name text NOT NULL, lat numeric(9,6) NULL, "
                "lng numeric(9,6) NULL, timezone text NULL, "
                "is_system boolean NOT NULL DEFAULT false"
            ),
        )
    )
    op.execute("""
    ALTER TABLE sites
      ADD CONSTRAINT uq_sites_id_tenant_id UNIQUE (id, tenant_id),
      ADD CONSTRAINT ck_sites_code CHECK (code <> ''),
      ADD CONSTRAINT ck_sites_name CHECK (name <> ''),
      ADD CONSTRAINT ck_sites_lat CHECK (lat BETWEEN -90 AND 90),
      ADD CONSTRAINT ck_sites_lng CHECK (lng BETWEEN -180 AND 180);

    CREATE UNIQUE INDEX uq_sites_tenant_id_upper_code
      ON sites (tenant_id, upper(code)) WHERE deleted_at IS NULL;

    REVOKE DELETE ON sites FROM aip_app;
    """)

    op.execute(
        render_template(
            "tenant_table",
            table="projects",
            columns=(
                "code text NOT NULL, name text NOT NULL, client_company_id uuid NULL, "
                "site_id uuid NULL, classification_id uuid NULL, template_id uuid NULL, "
                "region text NULL, timezone text NULL, currency char(3) NULL, "
                "status text NOT NULL, closed_at timestamptz NULL, "
                "sync_version integer NOT NULL DEFAULT 1"
            ),
        )
    )
    op.execute("""
    ALTER TABLE projects ALTER COLUMN status SET DEFAULT 'draft';
    ALTER TABLE projects
      ADD CONSTRAINT ck_projects_code CHECK (code <> ''),
      ADD CONSTRAINT ck_projects_name CHECK (name <> ''),
      ADD CONSTRAINT ck_projects_status
        CHECK (status IN ('draft', 'active', 'closing', 'archived')),
      ADD CONSTRAINT ck_projects_sync_version CHECK (sync_version >= 1),
      -- (site_id, tenant_id) so a project can never point at another tenant's site.
      ADD CONSTRAINT fk_projects_site_id_tenant_id_sites
        FOREIGN KEY (site_id, tenant_id) REFERENCES sites (id, tenant_id),
      ADD CONSTRAINT fk_projects_region_deployment_regions
        FOREIGN KEY (region) REFERENCES deployment_regions (code);

    CREATE UNIQUE INDEX uq_projects_tenant_id_upper_code
      ON projects (tenant_id, upper(code)) WHERE deleted_at IS NULL;
    CREATE INDEX ix_projects_tenant_id_status ON projects (tenant_id, status);
    CREATE INDEX ix_projects_tenant_id_site_id ON projects (tenant_id, site_id);

    REVOKE DELETE ON projects FROM aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
