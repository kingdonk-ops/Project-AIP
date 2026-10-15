"""SQLAlchemy Core table declarations for tenancy (TENANCY-01, ADR 0002).

Created only by the Alembic revision ``202610081122_tenancy_tenants_regions``; ``aip-db
check-schema`` compares them with the migrated database.

- ``deployment_regions``: global reference data (code PK, no ``tenant_id``, no RLS), read-only for
  the runtime roles.
- ``tenants``: ``id`` is the tenant id. FORCE RLS with ``id = app.tenant_id``, so inside
  ``with_tenant`` the app sees its own row only, and nothing when no tenant is set.
- ``tenant_subscription``, ``tenant_entitlement_override``, ``tenant_usage`` (ENT-01, revision
  ``202610151500_tenancy_entitlements``): tenant template tables with FORCE RLS.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP

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
    Column("is_real_customer", Boolean, nullable=False, server_default=text("false")),
    Column("status", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)


# --- ENT-01 (ADR 0008/0017/0023): revision 202610151500_tenancy_entitlements -------------------

_TS = TIMESTAMP(timezone=True)


def _standard() -> list[Column[datetime]]:
    return [
        Column("created_at", _TS, nullable=False, server_default=text("now()")),
        Column("updated_at", _TS, nullable=False, server_default=text("now()")),
        Column("deleted_at", _TS, nullable=True),
    ]


tenant_subscription = Table(
    "tenant_subscription",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, ForeignKey("tenants.id"), nullable=False, unique=True),
    Column("plan_code", Text, nullable=False),
    Column("plan_version", Integer, nullable=False),
    Column("term", Text, nullable=False),
    Column("starts_on", Date, nullable=False),
    Column("ends_on", Date, nullable=True),
    Column("renewal_date", Date, nullable=True),
    Column("seat_limits", JSONB, nullable=False, server_default=text("{}::jsonb")),
    Column("storage_gb", Integer, nullable=True),
    Column("add_ons", ARRAY(Text), nullable=False, server_default=text("{}::text[]")),
    Column("contract_ref", Text, nullable=True),
    Column("status", Text, nullable=False),
    Column("entitlement_version", BigInteger, nullable=False, server_default=text("1")),
    Column("updated_by", Uuid, nullable=True),
    *_standard(),
)

tenant_entitlement_override = Table(
    "tenant_entitlement_override",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, ForeignKey("tenants.id"), nullable=False),
    Column("key", Text, nullable=False),
    Column("value", JSONB, nullable=True),
    Column("reason", Text, nullable=False),
    Column("expires_at", _TS, nullable=True),
    Column("created_by", Uuid, nullable=True),
    *_standard(),
)

tenant_usage = Table(
    "tenant_usage",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, ForeignKey("tenants.id"), nullable=False),
    Column("period", Date, nullable=False),
    Column("active_users", JSONB, nullable=False, server_default=text("{}::jsonb")),
    Column("storage_bytes", BigInteger, nullable=False, server_default=text("0")),
    Column("jobs_count", BigInteger, nullable=False, server_default=text("0")),
    Column("ai_spend_cents", BigInteger, nullable=False, server_default=text("0")),
    Column("db_bytes_est", BigInteger, nullable=True),
    Column("db_estimate_method", Text, nullable=True),
    Column("db_estimated_at", _TS, nullable=True),
    Column("over_limit", JSONB, nullable=False, server_default=text("{}::jsonb")),
    Column("captured_at", _TS, nullable=False, server_default=text("now()")),
    *_standard(),
    UniqueConstraint("tenant_id", "period", name="uq_tenant_usage_tenant_id_period"),
)
