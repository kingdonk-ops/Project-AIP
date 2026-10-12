"""SQLAlchemy Core table declarations for access (ACCESS-01, ADR 0002).

Created only by the Alembic revision ``202610120445_access_permission_catalogue``.

- ``permission``: the global catalogue mirrored from module manifests (no ``tenant_id``, no RLS).
  ``aip_app`` may only SELECT; writes go through ``access_sync_permissions``.
- ``access_settings``: one live row per tenant with ``access_version`` (FORCE RLS, soft delete).
"""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Table, Text, Uuid, text

from aip.platform.db.metadata import metadata

permission = Table(
    "permission",
    metadata,
    Column("code", Text, primary_key=True),
    Column("module_id", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("is_privileged", Boolean, nullable=False, server_default=text("false")),
    Column("deprecated_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
)

access_settings = Table(
    "access_settings",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("access_version", BigInteger, nullable=False, server_default=text("1")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)
