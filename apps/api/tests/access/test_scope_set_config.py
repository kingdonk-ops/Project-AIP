"""ACCESS-03 unit tests for ``set_config_statements`` (no database).

``with_principal`` runs exactly these ``set_config`` calls, transaction-locally, to bind a principal
onto a tenant transaction so ``access_project_visible`` can see who is asking.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from aip.platform.db.scope import ScopePrincipal, SetConfig, set_config_statements

TENANT = UUID("00000000-0000-4000-8000-00000000000a")
USER = UUID("00000000-0000-4000-8000-0000000a11ce")


def _by_setting(statements: list[SetConfig]) -> dict[str, SetConfig]:
    return {s.setting: s for s in statements}


def test_user_principal_sets_tenant_kind_and_user_all_local() -> None:
    statements = set_config_statements(ScopePrincipal(TENANT, kind="user", user_id=USER))
    by_setting = _by_setting(statements)
    assert set(by_setting) == {"app.tenant_id", "app.principal_kind", "app.user_id"}
    assert by_setting["app.tenant_id"].value == str(TENANT)
    assert by_setting["app.principal_kind"].value == "user"
    assert by_setting["app.user_id"].value == str(USER)
    assert all(s.is_local for s in statements), "every set_config is transaction-local (is_local)"


def test_api_client_principal_sets_no_user_id() -> None:
    statements = set_config_statements(ScopePrincipal(TENANT, kind="api_client"))
    by_setting = _by_setting(statements)
    assert "app.user_id" not in by_setting
    assert by_setting["app.principal_kind"].value == "api_client"
    assert by_setting["app.tenant_id"].value == str(TENANT)


def test_system_principal_sets_no_user_id() -> None:
    statements = set_config_statements(ScopePrincipal(TENANT, kind="system"))
    assert "app.user_id" not in _by_setting(statements)
    assert _by_setting(statements)["app.principal_kind"].value == "system"


def test_user_principal_requires_a_user_id() -> None:
    with pytest.raises(ValueError, match="user principal needs a user_id"):
        ScopePrincipal(TENANT, kind="user")


def test_non_user_principal_rejects_a_user_id() -> None:
    with pytest.raises(ValueError, match="carries no user_id"):
        ScopePrincipal(TENANT, kind="system", user_id=USER)
