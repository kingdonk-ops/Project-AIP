"""SQLAlchemy Core declaration for the asset tree (ASSETS-01, ADR 0002).

Created only by the Alembic revision ``202610242000_assets_tree``; ``aip-db check-schema`` compares
this declaration with the migrated database. The table is tenant-scoped with soft delete and FORCE
ROW LEVEL SECURITY; ``aip_app`` has no DELETE (deletes are soft).

``path`` is a Postgres ``ltree`` column; ltree work goes through ``aip.platform.db.ltree`` with
``text()`` SQL (ADR 0002). asyncpg hands ltree back as a plain dotted string, so repository reads of
``select(assets)`` get ``path`` as ``str``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Column, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.types import UserDefinedType

from aip.platform.db.metadata import metadata


class Ltree(UserDefinedType[str]):
    """Postgres ``ltree`` (the materialised tree path), declared for ``aip-db check-schema``."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "ltree"


assets = Table(
    "assets",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("parent_id", UUID(as_uuid=True), nullable=True),
    Column("path", Ltree(), nullable=False),
    Column("internal_tag", Text, nullable=False),
    Column("tag_number", Text, nullable=True),
    Column("name", Text, nullable=False),
    Column("sort_order", Integer, nullable=False, server_default=text("0")),
    Column("created_by", UUID(as_uuid=True), nullable=True),
    Column("client_generated_id", UUID(as_uuid=True), nullable=True),
    Column("sync_version", Integer, nullable=False, server_default=text("1")),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", TIMESTAMP(timezone=True), nullable=True),
)
