"""PROJECTS-01 unit tests: request validation, lifecycle rules and the cursor codec."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aip.modules.projects.cursor import CursorCodec, InvalidCursorError
from aip.modules.projects.policies import can_transition
from aip.modules.projects.schemas import ProjectCreate, ProjectUpdate, SiteCreate
from aip.modules.projects.settings import ProjectsSettings


def error_locs(exc: ValidationError) -> list[tuple[int | str, ...]]:
    return [tuple(e["loc"]) for e in exc.errors()]


def test_create_upper_cases_the_code_and_defaults_to_draft() -> None:
    body = ProjectCreate.model_validate(
        {"code": "l592", "name": "Ichthys KIPS", "currency": "AUD", "timezone": "Australia/Perth"}
    )
    assert body.code == "L592"
    assert body.status == "draft"


@pytest.mark.parametrize(
    ("field", "value"),
    [("code", "ab cd"), ("code", "-L592"), ("currency", "XXX"), ("timezone", "Mars/Olympus")],
)
def test_invalid_fields_are_reported_at_their_path(field: str, value: str) -> None:
    body = {"code": "L592", "name": "Ichthys", field: value}
    with pytest.raises(ValidationError) as caught:
        ProjectCreate.model_validate(body)
    assert error_locs(caught.value) == [(field,)]


def test_create_cannot_start_archived_or_carry_unknown_fields() -> None:
    with pytest.raises(ValidationError) as caught:
        ProjectCreate.model_validate({"code": "L592", "name": "x", "status": "archived"})
    assert error_locs(caught.value) == [("status",)]
    with pytest.raises(ValidationError):
        ProjectCreate.model_validate({"code": "L592", "name": "x", "tenantId": "x"})


def test_update_needs_a_sync_version_and_rejects_null_for_required_fields() -> None:
    with pytest.raises(ValidationError) as caught:
        ProjectUpdate.model_validate({"name": "x"})
    assert error_locs(caught.value) == [("syncVersion",)]
    with pytest.raises(ValidationError, match="status cannot be null"):
        ProjectUpdate.model_validate({"syncVersion": 1, "status": None})
    body = ProjectUpdate.model_validate({"syncVersion": 2, "siteId": None, "name": "New"})
    assert body.changes(exclude=frozenset({"sync_version"})) == {"site_id": None, "name": "New"}


def test_site_coordinates_are_range_checked() -> None:
    with pytest.raises(ValidationError) as caught:
        SiteCreate.model_validate({"code": "S1", "name": "Site", "lat": 91, "lng": -181})
    assert sorted(error_locs(caught.value)) == [("lat",), ("lng",)]


def test_status_moves_forward_except_closing_back_to_active() -> None:
    assert can_transition("draft", "active")
    assert can_transition("active", "closing")
    assert can_transition("closing", "archived")
    assert can_transition("closing", "active")
    assert not can_transition("archived", "active")
    assert not can_transition("draft", "archived")
    assert not can_transition("active", "draft")
    assert not can_transition("draft", "draft")


def test_cursor_round_trips_and_rejects_tampering() -> None:
    codec = CursorCodec(b"k" * 32)
    data = {"code": "L592", "id": "0190a1b2-0000-7000-8000-000000000001"}
    cursor = codec.encode(data)
    assert codec.decode(cursor) == data

    body, _, mac = cursor.partition(".")
    tampered = codec.encode({**data, "code": "Z999"}).partition(".")[0] + "." + mac
    for bad in (tampered, body, "not-base64!.x", "", cursor[:-2]):
        with pytest.raises(InvalidCursorError):
            codec.decode(bad)
    with pytest.raises(InvalidCursorError):
        CursorCodec(b"other-key-of-32-bytes-0123456789").decode(cursor)


@pytest.mark.parametrize("env", ["production", "staging", "demo"])
def test_the_dev_cursor_key_is_refused_outside_dev_and_test(
    monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.delenv("PROJECTS_CURSOR_KEY", raising=False)
    monkeypatch.setenv("AIP_ENV", env)
    with pytest.raises(
        ValidationError, match=f"PROJECTS_CURSOR_KEY must be set when AIP_ENV={env}"
    ):
        ProjectsSettings()
    monkeypatch.setenv("PROJECTS_CURSOR_KEY", "a-real-secret-from-the-store-123")
    assert ProjectsSettings().cursor_key.get_secret_value().startswith("a-real")


@pytest.mark.parametrize("env", ["", "development", "test"])
def test_the_dev_cursor_key_is_allowed_in_dev_and_test(
    monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.delenv("PROJECTS_CURSOR_KEY", raising=False)
    monkeypatch.setenv("AIP_ENV", env)
    assert ProjectsSettings().aip_env == env


async def test_server_startup_fails_without_a_cursor_key_outside_dev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The check runs in the app lifespan, so a deploy fails at startup, not on a list request."""
    from aip.main import create_app
    from aip.modules.projects.settings import get_settings

    monkeypatch.delenv("PROJECTS_CURSOR_KEY", raising=False)
    monkeypatch.setenv("AIP_ENV", "staging")
    get_settings.cache_clear()
    app = create_app(env="test", tracing=False)
    try:
        with pytest.raises(ValidationError, match="PROJECTS_CURSOR_KEY"):
            async with app.router.lifespan_context(app):
                pass
    finally:
        get_settings.cache_clear()
