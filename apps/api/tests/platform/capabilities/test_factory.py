"""Unit tests for adapter selection, tenant keys and adapter config parsing (STACK-02)."""

from __future__ import annotations

import uuid

import pytest

from aip.platform.capabilities import (
    CapabilitySettings,
    SecretInConfigError,
    UnknownAdapterError,
    get_object_store,
    get_pdf_renderer,
    parse_adapter_config,
    tenant_key,
    validate_capability_settings,
)
from aip.platform.capabilities.adapters.gotenberg import GotenbergPdfRenderer
from aip.platform.capabilities.adapters.minio import MinioObjectStore
from aip.platform.capabilities.adapters.s3 import S3ObjectStore
from aip.platform.capabilities.protocols import ObjectStore, PdfRenderer

T1 = uuid.UUID("11111111-1111-4111-8111-111111111111")

# --- factory ------------------------------------------------------------------------------------


def test_minio_env_returns_minio_object_store(clean_capability_env: pytest.MonkeyPatch) -> None:
    clean_capability_env.setenv("OBJECT_STORE", "minio")
    clean_capability_env.setenv("OBJECT_STORE_ENDPOINT_URL", "http://rustfs:9000")
    store = get_object_store()
    assert isinstance(store, MinioObjectStore)
    assert isinstance(store, ObjectStore)


def test_s3_env_returns_s3_object_store(clean_capability_env: pytest.MonkeyPatch) -> None:
    clean_capability_env.setenv("OBJECT_STORE", "s3")
    store = get_object_store()
    assert isinstance(store, S3ObjectStore)
    assert not isinstance(store, MinioObjectStore)


def test_adapter_key_is_case_and_space_insensitive(
    clean_capability_env: pytest.MonkeyPatch,
) -> None:
    clean_capability_env.setenv("OBJECT_STORE", " S3 ")
    assert isinstance(get_object_store(), S3ObjectStore)


def test_unknown_object_store_names_variable_and_allowed_values(
    clean_capability_env: pytest.MonkeyPatch,
) -> None:
    clean_capability_env.setenv("OBJECT_STORE", "bogus")
    with pytest.raises(UnknownAdapterError) as excinfo:
        get_object_store()
    message = str(excinfo.value)
    assert "OBJECT_STORE" in message
    assert "bogus" in message
    assert "s3, minio" in message


def test_unknown_pdf_renderer_names_variable_and_allowed_values(
    clean_capability_env: pytest.MonkeyPatch,
) -> None:
    clean_capability_env.setenv("PDF_RENDERER", "wkhtmltopdf")
    with pytest.raises(UnknownAdapterError) as excinfo:
        get_pdf_renderer()
    assert "PDF_RENDERER" in str(excinfo.value)
    assert "gotenberg" in str(excinfo.value)


def test_gotenberg_env_returns_gotenberg_renderer(
    clean_capability_env: pytest.MonkeyPatch,
) -> None:
    clean_capability_env.setenv("PDF_RENDERER", "gotenberg")
    clean_capability_env.setenv("GOTENBERG_URL", "http://gotenberg:3000")
    clean_capability_env.setenv("GOTENBERG_TIMEOUT_S", "12.5")
    renderer = get_pdf_renderer()
    assert isinstance(renderer, GotenbergPdfRenderer)
    assert isinstance(renderer, PdfRenderer)
    assert renderer.base_url == "http://gotenberg:3000"
    assert renderer.timeout_s == 12.5
    assert renderer.max_bytes == 25 * 1024 * 1024


def test_defaults_without_env(clean_capability_env: pytest.MonkeyPatch) -> None:
    settings = CapabilitySettings()
    assert settings.object_store == "minio"
    assert settings.pdf_renderer == "gotenberg"
    assert settings.gotenberg_timeout_s == 30.0
    assert settings.gotenberg_max_bytes == 25 * 1024 * 1024
    validate_capability_settings(settings)


def test_credentials_are_secret_str(clean_capability_env: pytest.MonkeyPatch) -> None:
    clean_capability_env.setenv("OBJECT_STORE_SECRET_ACCESS_KEY", "hunter2-not-real")
    settings = CapabilitySettings()
    assert settings.object_store_secret_access_key is not None
    assert "hunter2-not-real" not in repr(settings)
    assert settings.object_store_secret_access_key.get_secret_value() == "hunter2-not-real"


def test_explicit_settings_override_env(clean_capability_env: pytest.MonkeyPatch) -> None:
    clean_capability_env.setenv("OBJECT_STORE", "bogus")
    store = get_object_store(CapabilitySettings(object_store="s3"))
    assert isinstance(store, S3ObjectStore)


def test_app_startup_fails_on_unknown_adapter(clean_capability_env: pytest.MonkeyPatch) -> None:
    from aip.main import create_app

    clean_capability_env.setenv("OBJECT_STORE", "bogus")
    with pytest.raises(UnknownAdapterError, match="OBJECT_STORE"):
        create_app()
    clean_capability_env.setenv("OBJECT_STORE", "minio")
    clean_capability_env.setenv("PDF_RENDERER", "bogus")
    with pytest.raises(UnknownAdapterError, match="PDF_RENDERER"):
        create_app()


def test_app_starts_with_known_adapters(clean_capability_env: pytest.MonkeyPatch) -> None:
    from aip.main import create_app

    clean_capability_env.setenv("OBJECT_STORE", "s3")
    clean_capability_env.setenv("PDF_RENDERER", "gotenberg")
    create_app()


# --- tenant keys --------------------------------------------------------------------------------


def test_tenant_key_builds_prefixed_key() -> None:
    assert tenant_key(T1, "uploads", "a.pdf") == f"tenant/{T1}/uploads/a.pdf"


def test_tenant_key_accepts_uuid_string_and_nested_part() -> None:
    assert tenant_key(str(T1), "uploads/2026", "a.pdf") == f"tenant/{T1}/uploads/2026/a.pdf"


@pytest.mark.parametrize(
    "parts",
    [
        ("..", "x"),
        (".", "x"),
        ("", "x"),
        ("uploads", ""),
        ("/etc", "passwd"),
        ("uploads/../x",),
        ("uploads//x",),
        ("uploads/",),
        ("a\\..\\b",),
        ("a\x00b",),
        (),
    ],
)
def test_tenant_key_rejects_unsafe_parts(parts: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        tenant_key(T1, *parts)


@pytest.mark.parametrize("tenant", ["", "not-a-uuid", "../other", f"{T1}/x"])
def test_tenant_key_rejects_bad_tenant(tenant: str) -> None:
    with pytest.raises(ValueError):
        tenant_key(tenant, "uploads", "a.pdf")


# --- adapter config -----------------------------------------------------------------------------


def test_parse_adapter_config_rejects_access_key() -> None:
    with pytest.raises(SecretInConfigError):
        parse_adapter_config({"access_key": "x"})


@pytest.mark.parametrize(
    "config",
    [
        {"secret": "x"},
        {"aws_secret_access_key": "x"},
        {"db_password": "x"},
        {"api_token": "x"},
        {"Access-Key": "x"},
        {"accessKey": "x"},
        {"nested": {"client_secret": "x"}},
        {"items": [{"refresh_token": "x"}]},
    ],
)
def test_parse_adapter_config_rejects_secret_like_keys(config: dict[str, object]) -> None:
    with pytest.raises(SecretInConfigError):
        parse_adapter_config(config)


def test_parse_adapter_config_error_does_not_echo_value() -> None:
    with pytest.raises(SecretInConfigError) as excinfo:
        parse_adapter_config({"password": "s3cr3t-value"})
    assert "s3cr3t-value" not in str(excinfo.value)
    assert "password" in str(excinfo.value)


def test_parse_adapter_config_accepts_non_secret_config() -> None:
    config = {"bucket": "aip", "region": "ap-southeast-2", "options": {"path_style": True}}
    parsed = parse_adapter_config(config)
    assert parsed == config
    assert parsed is not config
