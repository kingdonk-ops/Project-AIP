"""APPROVALS-08: ``ApprovalsApi.install_preset`` loads a ``config/workflows`` preset and publishes
it idempotently, so host modules ship their lifecycle as data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests.conftest import TENANT_A_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.approvals.api import ApprovalsApi
from aip.modules.approvals.presets import PresetError
from aip.modules.approvals.service import DefinitionsService
from aip.modules.approvals.tests.fixtures import demo_spec
from aip.platform.context import use_context

from .conftest import ctx

api = ApprovalsApi()
definitions = DefinitionsService()


def _write_preset(directory: Path, key: str, spec: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    body = {"key": key, "recordType": "widget", "spec": spec}
    (directory / f"{key}.json").write_text(json.dumps(body), encoding="utf-8")


@pytest.fixture
def workflows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "workflows"
    monkeypatch.setenv("AIP_WORKFLOWS_DIR", str(directory))
    return directory


async def test_install_preset_publishes_then_is_idempotent(db: TenantDb, workflows: Path) -> None:
    _write_preset(workflows, "widget_lifecycle", demo_spec())

    with use_context(ctx()):
        async with db.with_tenant(TENANT_A_ID) as conn:
            installed = await api.install_preset(conn, "widget_lifecycle")
    assert (installed.key, installed.record_type, installed.status) == (
        "widget_lifecycle",
        "widget",
        "active",
    )
    assert installed.version == 1

    # It is the tenant's active definition for the record type.
    with use_context(ctx()):
        async with db.with_tenant(TENANT_A_ID) as conn:
            active = await definitions.get_active_definition(conn, "widget")
    assert active.id == installed.id

    # Re-installing the unchanged preset is a no-op: same version, same id, no new draft.
    with use_context(ctx()):
        async with db.with_tenant(TENANT_A_ID) as conn:
            again = await api.install_preset(conn, "widget_lifecycle")
    assert (again.id, again.version) == (installed.id, 1)


async def test_install_preset_publishes_a_new_version_when_the_spec_changes(
    db: TenantDb, workflows: Path
) -> None:
    _write_preset(workflows, "widget_lifecycle", demo_spec())
    with use_context(ctx()):
        async with db.with_tenant(TENANT_A_ID) as conn:
            v1 = await api.install_preset(conn, "widget_lifecycle")

    changed = demo_spec()
    changed["states"][0]["labelKey"] = "approvals.demo.state.draft_v2"
    _write_preset(workflows, "widget_lifecycle", changed)
    with use_context(ctx()):
        async with db.with_tenant(TENANT_A_ID) as conn:
            v2 = await api.install_preset(conn, "widget_lifecycle")

    assert v2.id != v1.id
    assert v2.version == 2
    assert v2.status == "active"


async def test_install_preset_raises_for_an_unknown_preset(db: TenantDb, workflows: Path) -> None:
    with (
        use_context(ctx()),
        pytest.raises(PresetError, match="no workflow preset"),
    ):
        async with db.with_tenant(TENANT_A_ID) as conn:
            await api.install_preset(conn, "missing_lifecycle")
