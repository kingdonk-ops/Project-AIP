"""TESTING-04: generated IDOR and deny-by-default tests over every API route.

- Every route with a path parameter is listed in ``idor_routes.toml`` (a missing one fails the
  build). For each mapped route, tenant B's row is seeded by the DATABASE-07 generator and tenant
  A's admin (the real ``tenant_admin`` role through ``RoleGrantProvider``) calls the route with B's
  id: the answer is 403 or 404, never 2xx, and B's row is unchanged.
- Every ``requires()`` route answers 403 to a signed-in user with no grants (deny by default).
"""

from __future__ import annotations

import json
import re
import tomllib
import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg  # pyright: ignore[reportMissingTypeStubs]
import httpx
from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts

from aip.main import create_app
from aip.modules.access.tests.roles.conftest import ALICE, CAROL
from aip.platform.access.dependencies import access_declarations
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb
from tests.isolation.generator import cases, load_overrides, seed_pair

ROUTES_PATH = Path(__file__).with_name("idor_routes.toml")
_PARAM = re.compile(r"\{(\w+)\}")
_UUID_LITERAL = re.compile(r"^'([0-9a-f-]{36})'::uuid$")


def load_routes() -> dict[str, dict[str, Any]]:
    data = tomllib.loads(ROUTES_PATH.read_text(encoding="utf-8"))
    for key, entry in data.items():
        if entry.get("skip"):
            assert str(entry.get("reason", "")).strip(), f"{key}: a skipped route needs a reason"
        else:
            assert entry.get("table"), f"{key}: needs the table its id comes from"
        assert set(entry) <= {"table", "body", "query", "skip", "reason"}, key
    return data


def openapi_id_routes(application: FastAPI) -> list[str]:
    spec = application.openapi()
    return sorted(
        f"{method.upper()} {path}"
        for path, operations in spec["paths"].items()
        if _PARAM.search(path)
        for method in operations
    )


# --- unit -------------------------------------------------------------------------------------


def test_every_id_addressed_route_is_mapped_or_skipped_with_a_reason() -> None:
    routes = load_routes()
    live = openapi_id_routes(create_app(env="test", tracing=False))
    assert sorted(set(live) - set(routes)) == [], "add these to tests/access/idor_routes.toml"
    assert sorted(set(routes) - set(live)) == [], "these routes no longer exist"


def test_mapped_tables_are_tenant_tables_the_generator_can_seed() -> None:
    from aip.platform.db.migrator.cli import load_declared_tables

    known = {c.table for c in cases(load_declared_tables())}
    for key, entry in load_routes().items():
        if not entry.get("skip"):
            assert entry["table"] in known, key


# --- integration: IDOR ------------------------------------------------------------------------


async def _row(superuser_url: str, table: str, key: dict[str, str]) -> str | None:
    where = " AND ".join(f'"{c}" = {v}' for c, v in key.items())
    conn: Any = await asyncpg.connect(superuser_url)  # pyright: ignore[reportUnknownMemberType]
    try:
        return await conn.fetchval(f'SELECT row_to_json(t)::text FROM "{table}" t WHERE {where}')
    finally:
        await conn.close()


async def test_tenant_a_cannot_reach_tenant_bs_rows_through_any_id_route(
    app: FastAPI, db: TenantDb, client: httpx.AsyncClient
) -> None:
    overrides = load_overrides()
    by_table = {c.table: c for c in cases(_declared())}
    results: list[str] = []
    for key, entry in sorted(load_routes().items()):
        if entry.get("skip"):
            continue
        method, path = key.split(" ", 1)
        case = by_table[entry["table"]]
        _, key_b = await seed_pair(
            db.db.superuser_url, case, overrides.get(case.table), TENANT_A_ID, TENANT_B_ID
        )
        [id_column] = [c for c in case.primary_key if c != "created_at"]
        match = _UUID_LITERAL.match(key_b[id_column])
        assert match, f"{key}: {case.table} is not keyed by a uuid"
        b_id = UUID(match.group(1))
        before = await _row(db.db.superuser_url, case.table, key_b)

        url = _fill(path, b_id)
        if entry.get("query"):
            url = f"{url}?{entry['query']}"
        body = entry.get("body")
        res = await client.request(
            method,
            url,
            headers={**ALICE, **({"content-type": "application/json"} if body else {})},
            content=body.encode() if body else None,
        )
        after = await _row(db.db.superuser_url, case.table, key_b)
        if res.status_code not in (403, 404):
            results.append(f"{key}: tenant B's id returned {res.status_code} {res.text[:200]}")
        if after != before:
            results.append(f"{key}: tenant B's {case.table} row changed")
    assert results == []


def _fill(path: str, record_id: UUID) -> str:
    """The last path parameter is the record id; any earlier ones get random ids."""
    names = _PARAM.findall(path)
    for i, name in enumerate(names):
        value = record_id if i == len(names) - 1 else uuid.uuid4()
        path = path.replace("{" + name + "}", str(value), 1)
    return path


def _declared() -> Any:
    from aip.platform.db.migrator.cli import load_declared_tables

    return load_declared_tables()


# --- integration: deny by default -------------------------------------------------------------


async def test_a_user_with_no_grants_gets_403_from_every_requires_route(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    checked: list[str] = []
    failures: list[str] = []
    for ctx in iter_route_contexts(app.router.routes):
        path = ctx.path or ""
        if not isinstance(ctx.original_route, APIRoute) or not path.startswith("/api/v1"):
            continue
        kinds = {d.kind for d in access_declarations(ctx.dependant)}
        if "requires" not in kinds:
            continue
        url = _PARAM.sub(lambda _m: str(uuid.uuid4()), path)
        for method in sorted(set(ctx.methods or ()) - {"HEAD", "OPTIONS"}):
            res = await client.request(
                method,
                url,
                headers={**CAROL, "content-type": "application/json"},
                content=json.dumps({}).encode(),
            )
            checked.append(f"{method} {path}")
            if res.status_code != 403:
                failures.append(f"{method} {path}: {res.status_code}")
    assert len(checked) > 20
    assert failures == []
