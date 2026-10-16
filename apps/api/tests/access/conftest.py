"""TESTING-04 fixtures: the ACCESS-02 app (both fixture tenants seeded with users and their default
roles, alice and bob as tenant admins, the real ``RoleGrantProvider``) and the database fixtures."""

from aip.modules.access.tests.roles.conftest import app, client, db  # noqa: F401
from tests.fixtures.postgres import (  # noqa: F401
    bootstrapped_db,
    empty_db,
    migrated_db,
    pg_superuser_url,
    tenant_db,
)
