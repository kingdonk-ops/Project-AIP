"""SQLAlchemy Core table declarations for tenancy (TENANCY-01, ADR 0002).

Created only by the Alembic revision ``202610081122_tenancy_tenants_regions``; ``aip-db
check-schema`` compares them with the migrated database.

- ``deployment_regions``: global reference data (code PK, no ``tenant_id``, no RLS), read-only for
  the runtime roles.
- ``tenants``: ``id`` is the tenant id. FORCE RLS with ``id = app.tenant_id``, so inside
  ``with_tenant`` the app sees its own row only, and nothing when no tenant is set.
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Table, Text, Uuid

from aip.platform.db.metadata import metadata

deployment_regions = Table(
    "deployment_regions",
    metadata,
    Column("code", Text, primary_key=True),
    Column("label_key", Text, nullable=False),
    Column("in_country_only", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

tenants = Table(
    "tenants",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", Text, nullable=False),
    Column("slug", Text, nullable=False, unique=True),
    Column("deployment_shape", Text, nullable=False),
    Column("region_code", Text, ForeignKey("deployment_regions.code"), nullable=False),
    Column("kms_key_ref", Text, nullable=True),
    Column("status", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)
