"""SECURITY-09: FastAPI's API docs and OpenAPI schema are served only in development and test.

An allowlist (review 11 L4): production, the demo, staging and an unset ``AIP_ENV`` serve none.
"""

from __future__ import annotations

import httpx
import pytest

from aip.main import create_app

DOC_PATHS = ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc")


async def status_codes(env: str) -> dict[str, int]:
    app = create_app(env=env, tracing=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return {path: (await client.get(path)).status_code for path in DOC_PATHS}


@pytest.mark.parametrize("env", ["production", "demo", "staging", ""])
async def test_only_dev_and_test_serve_docs_or_schema(env: str) -> None:
    assert await status_codes(env) == dict.fromkeys(DOC_PATHS, 404)


@pytest.mark.parametrize("env", ["test", "development"])
async def test_dev_and_test_keep_the_docs(env: str) -> None:
    assert await status_codes(env) == dict.fromkeys(DOC_PATHS, 200)


def test_the_schema_is_still_built_in_process_for_codegen() -> None:
    schema = create_app(env="production", tracing=False).openapi()
    assert "/api/v1/health" in schema["paths"]
