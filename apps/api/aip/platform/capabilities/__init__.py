"""Capability interfaces and env-driven adapter selection (STACK-02).

Calling code asks for a capability and gets the protocol type::

    store = get_object_store()          # OBJECT_STORE=s3|minio
    renderer = get_pdf_renderer()       # PDF_RENDERER=gotenberg
    mailer = get_mailer()               # MAILER=smtp|ses (STACK-06; call it from a job only)

Swapping a library means adding one adapter file, one entry in the table below and changing the
environment variable. Calling code never changes. ``validate_capability_settings()`` runs at app
startup so an unknown adapter key stops the process with ``UnknownAdapterError``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from pydantic import SecretStr

from aip.platform.capabilities.adapters.gotenberg import GotenbergPdfRenderer
from aip.platform.capabilities.adapters.minio import MinioObjectStore
from aip.platform.capabilities.adapters.s3 import S3ObjectStore
from aip.platform.capabilities.adapters.ses import SesMailer
from aip.platform.capabilities.adapters.smtp import SmtpMailer
from aip.platform.capabilities.errors import (
    CapabilityError,
    MailError,
    ObjectNotFoundError,
    RenderError,
    RenderTimeoutError,
    RenderTooLargeError,
    SecretInConfigError,
    UnknownAdapterError,
)
from aip.platform.capabilities.keys import ObjectKey, tenant_key
from aip.platform.capabilities.protocols import (
    EmailMessage,
    IdentityProvider,
    Mailer,
    ObjectHead,
    ObjectStore,
    Ocr,
    PdfRenderer,
    PresignedPost,
    PresignedRequest,
    Sealer,
)
from aip.platform.capabilities.settings import CapabilitySettings, parse_adapter_config


def _secret(value: SecretStr | None) -> str | None:
    return value.get_secret_value() if value is not None else None


def _s3(settings: CapabilitySettings) -> ObjectStore:
    return S3ObjectStore(
        bucket=settings.object_store_bucket,
        region=settings.object_store_region,
        endpoint_url=settings.object_store_endpoint_url,
        access_key_id=_secret(settings.object_store_access_key_id),
        secret_access_key=_secret(settings.object_store_secret_access_key),
        addressing_style=settings.object_store_addressing_style,
    )


def _minio(settings: CapabilitySettings) -> ObjectStore:
    return MinioObjectStore(
        bucket=settings.object_store_bucket,
        region=settings.object_store_region,
        endpoint_url=settings.object_store_endpoint_url,
        access_key_id=_secret(settings.object_store_access_key_id),
        secret_access_key=_secret(settings.object_store_secret_access_key),
    )


def _gotenberg(settings: CapabilitySettings) -> PdfRenderer:
    return GotenbergPdfRenderer(
        settings.gotenberg_url,
        timeout_s=settings.gotenberg_timeout_s,
        max_bytes=settings.gotenberg_max_bytes,
    )


def _smtp(settings: CapabilitySettings) -> Mailer:
    return SmtpMailer(
        host=settings.smtp_host,
        port=settings.smtp_port,
        starttls=settings.smtp_starttls,
        username=settings.smtp_username,
        password=_secret(settings.smtp_password),
        timeout_s=settings.smtp_timeout_s,
    )


def _ses(settings: CapabilitySettings) -> Mailer:
    return SesMailer(
        region=settings.ses_region,
        endpoint_url=settings.ses_endpoint_url,
        configuration_set=settings.ses_configuration_set,
    )


OBJECT_STORE_ADAPTERS: Mapping[str, Callable[[CapabilitySettings], ObjectStore]] = {
    "s3": _s3,
    "minio": _minio,
}
PDF_RENDERER_ADAPTERS: Mapping[str, Callable[[CapabilitySettings], PdfRenderer]] = {
    "gotenberg": _gotenberg,
}

MAILER_ADAPTERS: Mapping[str, Callable[[CapabilitySettings], Mailer]] = {
    "smtp": _smtp,
    "ses": _ses,
}


def _pick[T](variable: str, value: str, adapters: Mapping[str, T]) -> T:
    try:
        return adapters[value]
    except KeyError:
        raise UnknownAdapterError(variable, value, adapters) from None


def validate_capability_settings(settings: CapabilitySettings | None = None) -> None:
    """Raise ``UnknownAdapterError`` if any configured adapter key is unknown. Called at startup."""
    settings = settings or CapabilitySettings()
    _pick("OBJECT_STORE", settings.object_store, OBJECT_STORE_ADAPTERS)
    _pick("PDF_RENDERER", settings.pdf_renderer, PDF_RENDERER_ADAPTERS)
    _pick("MAILER", settings.mailer, MAILER_ADAPTERS)


def get_object_store(settings: CapabilitySettings | None = None) -> ObjectStore:
    settings = settings or CapabilitySettings()
    return _pick("OBJECT_STORE", settings.object_store, OBJECT_STORE_ADAPTERS)(settings)


def get_pdf_renderer(settings: CapabilitySettings | None = None) -> PdfRenderer:
    settings = settings or CapabilitySettings()
    return _pick("PDF_RENDERER", settings.pdf_renderer, PDF_RENDERER_ADAPTERS)(settings)


def get_mailer(settings: CapabilitySettings | None = None) -> Mailer:
    settings = settings or CapabilitySettings()
    return _pick("MAILER", settings.mailer, MAILER_ADAPTERS)(settings)


__all__ = [
    "MAILER_ADAPTERS",
    "OBJECT_STORE_ADAPTERS",
    "PDF_RENDERER_ADAPTERS",
    "CapabilityError",
    "CapabilitySettings",
    "EmailMessage",
    "IdentityProvider",
    "MailError",
    "Mailer",
    "ObjectHead",
    "ObjectKey",
    "ObjectNotFoundError",
    "ObjectStore",
    "Ocr",
    "PdfRenderer",
    "PresignedPost",
    "PresignedRequest",
    "RenderError",
    "RenderTimeoutError",
    "RenderTooLargeError",
    "Sealer",
    "SecretInConfigError",
    "UnknownAdapterError",
    "get_mailer",
    "get_object_store",
    "get_pdf_renderer",
    "parse_adapter_config",
    "tenant_key",
    "validate_capability_settings",
]
