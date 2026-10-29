"""ASSETS-01 unit tests: the derived internal tag, Tag Number normalisation, request validation,
the event payload shape and the cursor-key settings guard. ASSETS-02: typed-asset request shapes,
the attribute error mapping and the untyped-attributes guard."""

from __future__ import annotations

import re
from uuid import UUID

import pytest
from pydantic import ValidationError

from aip.modules.assets.events import AssetEvent
from aip.modules.assets.policies import internal_tag, normalise_tag_number
from aip.modules.assets.schemas import AssetCreate, AssetUpdate
from aip.modules.assets.service import attribute_errors, create_asset_on
from aip.modules.assets.settings import AssetsSettings
from aip.modules.item_types.api import AttributeValidationError
from aip.platform.http.errors import DomainError

_TAG_RE = re.compile(r"^AT-[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}$")


def error_locs(exc: ValidationError) -> list[tuple[int | str, ...]]:
    return [tuple(e["loc"]) for e in exc.errors()]


def test_internal_tag_is_crockford_and_stable() -> None:
    asset_id = UUID("0192f3c4-5e6f-7abc-8def-0123456789ab")
    tag = internal_tag(asset_id)
    assert _TAG_RE.fullmatch(tag)
    assert internal_tag(asset_id) == tag  # deterministic


def test_internal_tag_depends_only_on_the_low_60_bits() -> None:
    # Two ids sharing their low 60 bits get the same tag; the unique index is the real guard.
    base = UUID("0192f3c4-5e6f-7abc-8def-0123456789ab")
    same_low = UUID(int=(0xABCD << 60) | (base.int & ((1 << 60) - 1)))
    assert internal_tag(base) == internal_tag(same_low)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("  P-101 ", "P-101"), ("P  101", "P 101"), ("   ", None), (None, None), ("P-101", "P-101")],
)
def test_tag_number_normalisation(raw: str | None, expected: str | None) -> None:
    assert normalise_tag_number(raw) == expected


def test_create_rejects_unknown_fields_like_internal_tag() -> None:
    with pytest.raises(ValidationError) as caught:
        AssetCreate.model_validate({"name": "Pump", "internalTag": "X"})
    assert error_locs(caught.value) == [("internalTag",)]


def test_create_normalises_the_tag_number() -> None:
    body = AssetCreate.model_validate({"name": "Pump", "tagNumber": "  p 101 "})
    assert body.tag_number == "p 101"
    blank = AssetCreate.model_validate({"name": "Pump", "tagNumber": "   "})
    assert blank.tag_number is None


def test_update_needs_a_sync_version_and_rejects_null_name_or_reparenting() -> None:
    with pytest.raises(ValidationError) as caught:
        AssetUpdate.model_validate({"name": "x"})
    assert error_locs(caught.value) == [("syncVersion",)]
    with pytest.raises(ValidationError, match="name cannot be null"):
        AssetUpdate.model_validate({"syncVersion": 1, "name": None})
    for field in ("internalTag", "path", "parentId"):
        with pytest.raises(ValidationError):
            AssetUpdate.model_validate({"syncVersion": 1, field: "x"})


def test_asset_event_round_trips_with_camel_case_keys() -> None:
    payload = {
        "assetId": "0192f3c4-5e6f-7abc-8def-0123456789ab",
        "internalTag": "AT-0000-0000-0000",
        "tagNumber": None,
        "parentId": None,
        "before": None,
        "after": {"name": "Site A"},
    }
    dumped = AssetEvent.model_validate(payload).model_dump(mode="json")
    assert set(dumped) == {"assetId", "internalTag", "tagNumber", "parentId", "before", "after"}
    assert dumped["after"] == {"name": "Site A"}


@pytest.mark.parametrize("env", ["production", "staging", "demo"])
def test_the_dev_cursor_key_is_refused_outside_dev_and_test(
    monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.delenv("ASSETS_CURSOR_KEY", raising=False)
    monkeypatch.setenv("AIP_ENV", env)
    with pytest.raises(ValidationError, match=f"ASSETS_CURSOR_KEY must be set when AIP_ENV={env}"):
        AssetsSettings()
    monkeypatch.setenv("ASSETS_CURSOR_KEY", "a-real-secret-from-the-store-123")
    assert AssetsSettings().cursor_key.get_secret_value().startswith("a-real")


# --- ASSETS-02 ---------------------------------------------------------------------------------


def test_the_pinned_version_is_never_accepted_in_a_body() -> None:
    version = "0192f3c4-5e6f-7abc-8def-0123456789ab"
    with pytest.raises(ValidationError) as caught:
        AssetCreate.model_validate({"name": "P-101", "itemTypeVersionId": version})
    assert error_locs(caught.value) == [("itemTypeVersionId",)]
    with pytest.raises(ValidationError):
        AssetUpdate.model_validate({"syncVersion": 1, "itemTypeVersionId": version})


def test_update_refuses_null_attributes_but_allows_clearing_the_type() -> None:
    with pytest.raises(ValidationError, match="attributes cannot be null"):
        AssetUpdate.model_validate({"syncVersion": 1, "attributes": None})
    cleared = AssetUpdate.model_validate({"syncVersion": 1, "itemTypeId": None})
    assert cleared.changes() == {"item_type_id": None}


def test_attribute_errors_map_to_field_paths_and_keyword_codes() -> None:
    errors = [
        AttributeValidationError(path="$.diameter_mm", term_key="validation.attribute.required"),
        AttributeValidationError(
            path="$.service", term_key="validation.attribute.enum", params={"enum": ["water"]}
        ),
    ]
    assert attribute_errors(errors) == [
        {"path": "attributes.diameter_mm", "code": "required"},
        {"path": "attributes.service", "code": "enum"},
    ]


class _NoSql:
    """A connection stand-in that fails the test on any use."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"SQL attempted: conn.{name}")


async def test_attributes_without_a_type_are_refused_before_any_sql() -> None:
    data = AssetCreate.model_validate({"name": "Folder", "attributes": {"x": 1}})
    with pytest.raises(DomainError) as caught:
        await create_asset_on(_NoSql(), None, data)  # type: ignore[arg-type]
    assert (caught.value.status_code, caught.value.code) == (422, "ATTRIBUTES_WITHOUT_TYPE")
