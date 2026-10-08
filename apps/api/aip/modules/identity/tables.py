"""SQLAlchemy Core table declarations for identity (ADR 0002).

``login_directory`` is the one global, pre-tenant table (ADR 0005): no ``tenant_id`` RLS, no soft
delete. Declared only so ``aip-db check-schema`` matches the migration; the application never
queries it directly (``aip_app`` has no privileges on it) and reads through
``identity_resolve_login`` instead (see ``repository.py``).
"""

from sqlalchemy import Column, DateTime, Table, Text, Uuid
from sqlalchemy.dialects.postgresql import CITEXT

from aip.platform.db.metadata import metadata

login_directory = Table(
    "login_directory",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("kind", Text, nullable=False),
    Column("key", CITEXT, nullable=False),
    Column("tenant_id", Uuid, nullable=False),
    Column("idp_alias", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
