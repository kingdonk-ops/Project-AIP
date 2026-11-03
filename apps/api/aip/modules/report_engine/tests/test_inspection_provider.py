"""REPORTS-03 unit tests: the ``inspection`` data provider on fake published interfaces (no
database).

``fixtures/inspection-coating.json`` is what the inspections, assets, projects, forms, identity and
uploads interfaces return for one approved inspection of FORMS-01's ``coating-itr-min`` form:
``surface_prepared = true``, ``dft_avg`` 0.2 mm (failed), two photos, ``remarks`` hidden by its
``visibleIf`` and no signature yet.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.assets.api import AssetOut
from aip.modules.forms.api import FormRevisionOut
from aip.modules.inspections.api import CurrentResponses, InspectionOut
from aip.modules.projects.api import ProjectOut
from aip.modules.report_engine.providers import RecordNotFound, ReportSource
from aip.modules.report_engine.providers.inspection import InspectionDeps, InspectionProvider
from aip.modules.uploads.api import StoredFileRef

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "inspection-coating.json"
CONN = cast(AsyncConnection, object())
SAM = UUID("00000000-0000-4000-8000-0000000005e1")
JPEG, PDF = "image/jpeg", "application/pdf"


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text("utf-8"))


class Fakes:
    """The published interfaces, answering from the fixture (tests may change ``data``)."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.label_requests: list[list[str]] = []

    async def get_inspection(self, conn: AsyncConnection, id: UUID) -> InspectionOut | None:
        row = self.data["inspection"]
        return None if row is None else InspectionOut.model_validate(row)

    async def get_current_responses(
        self, conn: AsyncConnection, id: UUID
    ) -> CurrentResponses | None:
        return CurrentResponses.model_validate(self.data["responses"])

    async def get_asset(self, conn: AsyncConnection, id: UUID) -> AssetOut | None:
        return AssetOut.model_validate(self.data["asset"])

    async def get_ancestor_names(self, conn: AsyncConnection, id: UUID) -> list[str]:
        return list(self.data["location"])

    async def get_project(self, conn: AsyncConnection, id: UUID) -> ProjectOut | None:
        return ProjectOut.model_validate(self.data["project"])

    async def get_revision(self, conn: AsyncConnection, id: UUID) -> FormRevisionOut | None:
        return FormRevisionOut.from_row(self.data["revision"])

    async def get_display_names(
        self, conn: AsyncConnection, ids: Iterable[UUID]
    ) -> dict[UUID, str]:
        users = {UUID(k): v for k, v in self.data["users"].items()}
        return {i: users[i] for i in ids if i in users}

    async def get_stored_file(self, conn: AsyncConnection, id: UUID) -> StoredFileRef | None:
        found = self.data["files"].get(str(id))
        if found is None:
            return None
        return StoredFileRef(
            id=id,
            project_id=None,
            filename=None,
            content_type=found["contentType"],
            size_bytes=found["sizeBytes"],
            sha256="0" * 64,
            source="upload",
            purpose=None,
            created_at=datetime(2026, 10, 30, tzinfo=UTC),
        )

    async def resolve_labels(
        self, conn: AsyncConnection, keys: list[str], project_id: UUID | None
    ) -> dict[str, str]:
        self.label_requests.append(keys)
        return {k: v for k, v in self.data["labels"].items() if k in keys}

    def deps(self) -> InspectionDeps:
        return InspectionDeps(
            get_inspection=self.get_inspection,
            get_current_responses=self.get_current_responses,
            get_asset=self.get_asset,
            get_ancestor_names=self.get_ancestor_names,
            get_project=self.get_project,
            get_revision=self.get_revision,
            get_display_names=self.get_display_names,
            get_stored_file=self.get_stored_file,
            resolve_labels=self.resolve_labels,
        )


async def _provide(data: dict[str, Any], context: dict[str, Any] | None = None) -> ReportSource:
    provider = InspectionProvider(Fakes(data).deps())
    inspection_id = UUID(data["inspection"]["id"]) if data["inspection"] else UUID(int=1)
    return await provider(CONN, inspection_id, context=context or {})


def _fields(source: ReportSource) -> dict[str, dict[str, Any]]:
    return {f["key"]: f for s in source.data["form"]["sections"] for f in s["fields"]}


def _photos(data: dict[str, Any], files: list[tuple[str, int]]) -> None:
    """Answer the ``photos`` field with ``files`` (content type, size) in order."""
    refs = []
    for n, (content_type, size) in enumerate(files):
        file_id = str(UUID(int=0xF000 + n))
        data["files"][file_id] = {"contentType": content_type, "sizeBytes": size}
        refs.append({"fileId": file_id})
    data["responses"]["answers"]["photos"]["value"] = refs


async def test_the_coating_fixture_gives_the_visible_fields_and_two_photos() -> None:
    source = await _provide(_fixture())
    fields = _fields(source)
    assert list(fields) == ["surface_prepared", "blast_standard", "dft_avg", "photos", "signature"]
    assert source.data["summary"] == {"answered": 4, "failed": 1, "missingRequired": 0}
    assert fields["dft_avg"]["answer"] == {"valueSi": 0.2, "unit": "mm"}  # mm is the SI unit
    assert fields["dft_avg"]["failed"] is True and fields["surface_prepared"]["failed"] is False
    assert fields["blast_standard"]["answer"] == "Sa 2.5"  # the option label
    assert fields["surface_prepared"]["answer"] is True
    assert fields["signature"]["answer"] is None and fields["signature"]["respondedBy"] is None
    assert fields["dft_avg"]["respondedBy"] == "Ivy Inspector"
    assert fields["dft_avg"]["respondedAt"] == "2026-10-30T01:20:00Z"
    assert [f.role for f in source.files] == ["photo:photos", "photo:photos"]
    first = str(source.files[0].file_id)
    assert fields["photos"]["answer"][0] == {"fileId": first, "asset": f"file-{first}.jpg"}
    assert fields["photos"]["answer"][1]["asset"].endswith(".png")


async def test_the_record_carries_asset_project_form_and_the_register_label() -> None:
    source = await _provide(_fixture())
    data = source.data
    assert data["asset"] == {
        "tagNumber": "P-1001",
        "name": "Process line P-1001",
        "internalTag": "AS-000123",
        "location": ["Karratha compressor station", "Train 1"],
    }
    assert data["project"] == {
        "code": "KF-01",
        "name": "Karratha compressor station",
        "timezone": "Australia/Perth",
    }
    assert data["form"]["code"] == "coating-itr-min" and data["form"]["revisionNo"] == 1
    assert data["inspection"]["state"] == "performed"
    assert data["approval"] == {}  # a manual render has no approval
    assert source.record_version == 7 and source.time_zone_hint == "Australia/Perth"
    assert source.label == "KF-01 P-1001 Process line P-1001"
    json.dumps(data)  # plain JSON only


async def test_the_trigger_context_fills_the_approval() -> None:
    occurred = datetime(2026, 10, 30, 3, 0, tzinfo=UTC)
    source = await _provide(_fixture(), {"approvedAt": occurred, "approvedBy": SAM})
    assert source.data["approval"] == {
        "approvedAt": "2026-10-30T03:00:00Z",
        "approvedBy": "Sam Supervisor",
    }


async def test_a_label_key_is_resolved_into_display_text() -> None:
    data = _fixture()
    fields = data["revision"]["schema"]["sections"][1]["fields"]
    fields[0]["labelKey"] = "coating.dft_average"
    fakes = Fakes(data)
    source = await InspectionProvider(fakes.deps())(
        CONN, UUID(data["inspection"]["id"]), context={}
    )
    assert _fields(source)["dft_avg"]["label"] == "Average DFT (coating)"
    assert fakes.label_requests == [["coating.dft_average"]]


async def test_at_most_40_images_are_embedded() -> None:
    data = _fixture()
    _photos(data, [(JPEG, 1000)] * 41)
    source = await _provide(data)
    answer = _fields(source)["photos"]["answer"]
    assert len(source.files) == 40
    assert [a for a in answer if "omitted" in a] == [
        {"fileId": answer[40]["fileId"], "omitted": "too_many"}
    ]


@pytest.mark.parametrize(
    ("content_type", "size", "reason"),
    [(JPEG, 4 * 1024 * 1024, "too_large"), (PDF, 1000, "not_an_image")],
)
async def test_a_file_that_cannot_be_embedded_is_omitted(
    content_type: str, size: int, reason: str
) -> None:
    data = _fixture()
    _photos(data, [(content_type, size)])
    source = await _provide(data)
    (answer,) = _fields(source)["photos"]["answer"]
    assert answer["omitted"] == reason and "asset" not in answer
    assert source.files == ()


async def test_a_missing_file_is_unavailable_not_an_error() -> None:
    data = _fixture()
    data["responses"]["answers"]["photos"]["value"] = [{"fileId": str(UUID(int=0xDEAD))}]
    source = await _provide(data)
    assert _fields(source)["photos"]["answer"][0]["omitted"] == "unavailable"


async def test_an_unknown_inspection_is_record_not_found() -> None:
    data = copy.deepcopy(_fixture())
    data["inspection"] = None
    with pytest.raises(RecordNotFound):
        await _provide(data)
