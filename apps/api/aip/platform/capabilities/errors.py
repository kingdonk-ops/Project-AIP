"""Errors raised by capability factories and adapters (STACK-02)."""

from __future__ import annotations

from collections.abc import Iterable


class CapabilityError(Exception):
    """Base class for capability errors."""


class UnknownAdapterError(CapabilityError):
    """An environment variable selects an adapter that does not exist. Stops app startup."""

    def __init__(self, variable: str, value: str, allowed: Iterable[str]) -> None:
        self.variable = variable
        self.value = value
        self.allowed = tuple(allowed)
        allowed_list = ", ".join(self.allowed)
        super().__init__(
            f"{variable}={value!r} is not a known adapter; allowed values: {allowed_list}"
        )


class SecretInConfigError(CapabilityError):
    """Stored adapter config contains a secret-like key. Secrets come only from the environment."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"adapter config key {path!r} looks like a secret; "
            "secrets must come from environment variables, never from stored config"
        )


class ObjectNotFoundError(CapabilityError):
    """The object store has no object under this key."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"object not found: {key}")


class RenderError(CapabilityError):
    """The PDF renderer failed."""


class RenderTimeoutError(RenderError):
    """The PDF renderer did not answer within the request timeout."""


class RenderTooLargeError(RenderError):
    """The rendered PDF exceeds the response size cap."""
