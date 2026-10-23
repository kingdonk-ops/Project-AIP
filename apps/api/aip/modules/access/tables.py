"""SQLAlchemy Core table declarations for access (ACCESS-01, ADR 0002).

Created only by the Alembic revision ``202610120445_access_permission_catalogue``.

- ``permission``: the global catalogue mirrored from module manifests (no ``tenant_id``, no RLS).
  ``aip_app`` may only SELECT; writes go through ``access_sync_permissions``.
- ``access_settings``: one live row per tenant with ``access_version`` (FORCE RLS, soft delete).

ACCESS-02 (revision ``202610131400_access_roles``): ``role``, ``role_permission`` and
``role_assignment``, all tenant tables (FORCE RLS, soft delete; ``aip_app`` cannot DELETE).

ACCESS-03 (revision ``202610191000_access_scope_rls``): ``access_user_scope``, the denormalised
project/tenant scope maintained by a trigger on ``role_assignment`` and read by the RLS predicate
``access_project_visible``. Declared here so ``aip-db check-schema`` sees it.
"""

from typing import Any

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Table, Text, Uuid, text
from sqlalchemy.types import UserDefinedType

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


class Ltree(UserDefinedType[str]):
    """Postgres ``ltree`` (asset subtree paths), declared for ``aip-db check-schema``."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "ltree"


role = Table(
    "role",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("code", Text, nullable=False),
    Column("name_term_key", Text, nullable=True),
    Column("name", Text, nullable=True),
    Column("is_system", Boolean, nullable=False, server_default=text("false")),
    Column("customised_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)

role_permission = Table(
    "role_permission",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("role_id", Uuid, nullable=False),
    Column("permission_code", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)

role_assignment = Table(
    "role_assignment",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("user_id", Uuid, nullable=False),
    Column("role_id", Uuid, nullable=False),
    Column("scope_type", Text, nullable=False),
    Column("project_id", Uuid, nullable=True),
    Column("team_id", Uuid, nullable=True),
    Column("asset_path", Ltree(), nullable=True),
    Column("source", Text, nullable=False, server_default=text("'manual'")),
    Column("valid_from", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("valid_to", DateTime(timezone=True), nullable=True),
    Column("approved_by", Uuid, nullable=True),
    Column("created_by", Uuid, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)

access_user_scope = Table(
    "access_user_scope",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("user_id", Uuid, nullable=False),
    Column("scope_kind", Text, nullable=False),
    Column("project_id", Uuid, nullable=True),
    Column("role_assignment_id", Uuid, nullable=False),
    Column("valid_from", DateTime(timezone=True), nullable=False),
    Column("valid_to", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)
