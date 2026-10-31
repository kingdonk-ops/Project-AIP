"""INSPECTIONS-01 unit tests: strict request bodies, the guard facts and the term keys."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from aip.modules.inspections.schemas import InspectionCreate, TransitionBody
from aip.modules.inspections.workflow import facts_of

MODULE_DIR = Path(__file__).resolve().parents[1]
TERMS = MODULE_DIR.parents[4] / "config" / "terms" / "en-AU" / "inspections.json"
ASSET = "00000000-0000-4000-8000-0000000a55e7"
TEMPLATE = "00000000-0000-4000-8000-00000000f0a1"
# A term key in source: a quoted inspection.<group>.<code> label or message key.
TERM_KEY_RE = re.compile(r"\"(inspection\.(?:error|source|kind|status)\.[a-z_]+)\"")


def test_create_rejects_a_client_supplied_state() -> None:
    body = {"assetId": ASSET, "templateId": TEMPLATE, "kind": "inspection", "state": "completed"}
    with pytest.raises(ValidationError) as caught:
        InspectionCreate.model_validate(body)
    assert [e["loc"] for e in caught.value.errors()] == [("state",)]


@pytest.mark.parametrize("key", ["source", "sourceRefId", "itpParentId", "workflowInstanceId"])
def test_create_rejects_server_owned_fields(key: str) -> None:
    body = {"assetId": ASSET, "templateId": TEMPLATE, "kind": "inspection", key: ASSET}
    with pytest.raises(ValidationError) as caught:
        InspectionCreate.model_validate(body)
    assert [e["loc"] for e in caught.value.errors()] == [(key,)]


def test_an_unknown_kind_lists_the_allowed_kinds() -> None:
    with pytest.raises(ValidationError) as caught:
        InspectionCreate.model_validate({"assetId": ASSET, "templateId": TEMPLATE, "kind": "audit"})
    (error,) = caught.value.errors()
    assert error["loc"] == ("kind",)
    for kind in ("inspection", "itp", "rfi"):
        assert f"'{kind}'" in error["msg"]


def test_a_transition_body_is_strict() -> None:
    with pytest.raises(ValidationError):
        TransitionBody.model_validate({"action": "ready", "toState": "performed"})
    body = TransitionBody.model_validate({"action": "ready", "expectedSyncVersion": 2})
    assert (body.action, body.expected_sync_version, body.comment) == ("ready", 2, None)


def test_the_facts_are_exactly_kind_asset_project_and_source_as_json() -> None:
    row: dict[str, Any] = {
        "id": UUID("00000000-0000-4000-8000-0000000001a1"),
        "kind": "itp",
        "asset_id": UUID(ASSET),
        "project_id": UUID("00000000-0000-4000-8000-00000000af01"),
        "source": "reinspection",
        "source_ref_id": UUID("00000000-0000-4000-8000-0000000001a0"),
        "state": "draft",
        "created_at": datetime.now(UTC),
    }
    facts = facts_of(row)
    assert facts == {
        "kind": "itp",
        "assetId": ASSET,
        "projectId": "00000000-0000-4000-8000-00000000af01",
        "source": "reinspection",
    }
    assert json.loads(json.dumps(facts)) == facts
    assert facts_of({**row, "project_id": None})["projectId"] is None


def test_every_referenced_term_key_exists() -> None:
    terms = json.loads(TERMS.read_text(encoding="utf-8"))
    referenced: set[str] = set()
    for name in ("schemas.py", "service.py"):
        referenced |= set(TERM_KEY_RE.findall((MODULE_DIR / name).read_text(encoding="utf-8")))
    assert referenced  # the scan found the error message keys
    assert sorted(referenced - set(terms)) == []


def test_every_kind_and_source_has_a_label() -> None:
    from aip.modules.inspections.schemas import KINDS, SOURCES

    terms = json.loads(TERMS.read_text(encoding="utf-8"))
    missing = [f"inspection.kind.{k}" for k in KINDS if f"inspection.kind.{k}" not in terms]
    missing += [f"inspection.source.{s}" for s in SOURCES if f"inspection.source.{s}" not in terms]
    assert missing == []
