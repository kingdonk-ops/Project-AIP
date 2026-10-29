"""Fixtures for the ACCESS-04 tests: the ACCESS-02 app and seed, plus a clean policy cache."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from tests.fixtures.postgres import outbox  # noqa: F401 # pyright: ignore[reportUnusedImport]
from tests.fixtures.redis import redis_server  # noqa: F401 # pyright: ignore[reportUnusedImport]

from aip.modules.access.api import configure_policy_cache

from ..roles.conftest import (  # noqa: F401 - re-exported pytest fixtures
    app,  # pyright: ignore[reportUnusedImport]
    client,  # pyright: ignore[reportUnusedImport]
    db,  # pyright: ignore[reportUnusedImport]
)


@pytest.fixture(autouse=True)
def _fresh_policy_cache(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No Redis unless a test wires one; never leak a configured cache into another test."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    configure_policy_cache(None)
    yield
    configure_policy_cache(None)
