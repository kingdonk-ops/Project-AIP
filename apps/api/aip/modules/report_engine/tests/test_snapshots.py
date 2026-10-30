"""REPORTS-02 unit tests: the snapshot body and its hash (no database).

The hash is taken over the RFC 8785 canonical JSON, so key order never matters, any data change
does, and the body holds no clock value. A body over 5 MB is refused.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest

from aip.modules.report_engine.snapshots import SNAPSHOT_MAX_BYTES, hash_body, snapshot_body
from aip.platform.http import DomainError

RECORD_ID = UUID("00000000-0000-4000-8000-0000000000a1")


def _body(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "record_type": "project",
        "record_id": RECORD_ID,
        "record_version": 3,
        "record": {"project": {"code": "KF-01", "name": "Gorgon", "status": "active"}},
        "labels": {"projects.status.active": "Completed", "report.label.page": "Page"},
        "locale": "en-AU",
        "time_zone": "Australia/Perth",
        "unit_system": "metric",
        "files": [],
    }
    values.update(overrides)
    return snapshot_body(**values)


def _reordered(value: Any) -> Any:
    if isinstance(value, dict):
        items = list(value.items())[::-1]  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportUnknownVariableType]
        return {k: _reordered(v) for k, v in items}  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, list):
        return [_reordered(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
    return value


def test_the_body_has_the_documented_shape() -> None:
    body = _body()
    assert list(body) == [
        "schemaVersion",
        "recordType",
        "recordId",
        "recordVersion",
        "record",
        "labels",
        "locale",
        "timeZone",
        "unitSystem",
        "files",
    ]
    assert body["schemaVersion"] == 1 and body["recordId"] == str(RECORD_ID)
    json.dumps(body)  # plain JSON only


def test_key_order_does_not_change_the_hash() -> None:
    body = _body()
    reordered = _reordered(body)
    assert list(reordered) != list(body)
    assert hash_body(reordered) == hash_body(body)


def test_the_same_data_twice_gives_the_same_hash() -> None:
    assert hash_body(_body()) == hash_body(_body())


def test_changing_one_label_changes_the_hash() -> None:
    complete = _body(labels={"projects.status.active": "Complete", "report.label.page": "Page"})
    digest, size = hash_body(_body())
    assert len(digest) == 64 and size > 0
    assert hash_body(complete)[0] != digest


def test_a_six_megabyte_body_is_refused() -> None:
    big = _body(record={"blob": "x" * (6 * 1024 * 1024)})
    with pytest.raises(DomainError) as excinfo:
        hash_body(big)
    assert (excinfo.value.status_code, excinfo.value.code) == (422, "SNAPSHOT_TOO_LARGE")


def test_a_body_just_under_the_cap_is_accepted() -> None:
    small = _body(record={"blob": "x" * (SNAPSHOT_MAX_BYTES - 4096)})
    assert hash_body(small)[1] <= SNAPSHOT_MAX_BYTES
