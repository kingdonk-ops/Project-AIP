"""TERMS-02: the resolver, its fallback chain, the Redis cache and its invalidation.

Unit tests exercise the pure merge (``Layers``/``resolve_from``). Integration tests load the
shipped en-AU defaults as ``aip_owner``, then resolve and write through ``aip_app``
(``tenant_db``, RLS on) with a real Redis cache; the pack test runs the real outbox dispatcher
(claims as ``aip_jobs``).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from structlog.testing import capture_logs
from tests.conftest import ALICE_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import JOBS, REPO_ROOT, FreshDb, TenantDb
from tests.fixtures.redis import RedisServer

from aip.modules.terms import api
from aip.modules.terms.cache import NullTermsCache, RedisTermsCache, configure_cache
from aip.modules.terms.loader import load
from aip.modules.terms.service import (
    Layers,
    PackNotFoundError,
    TenantMismatchError,
    activate_pack_version,
    bulk_resolve,
    resolve,
    resolve_from,
    set_override,
)
from aip.platform.context import RequestContext, use_context
from aip.platform.db.engine import EngineSettings, create_app_engine
from aip.platform.events.dispatcher import dispatch_batch
from aip.platform.events.subscribers import subscribers
from aip.platform.terms import register_term_resolver, term_resolver

EN_AU = REPO_ROOT / "config" / "terms" / "en-AU"
HOLD = "itp.point_type.hold"
RIO_CLIENT = UUID("00000000-0000-4000-8000-0000000001a0")
RIO_PROJECT = UUID("00000000-0000-4000-8000-0000000001a1")
OTHER_PROJECT = UUID("00000000-0000-4000-8000-0000000001b1")


# --- unit: the merge and fallback chain --------------------------------------------------------


def test_project_text_beats_tenant_text() -> None:
    layers = Layers(
        tenant={"en-AU": {HOLD: "Hold point"}}, project={"en-AU": {HOLD: "Project hold"}}
    )
    assert resolve_from(layers, [HOLD], "en-AU", TENANT_A_ID) == {HOLD: "Project hold"}


def test_precedence_is_project_client_tenant() -> None:
    layers = Layers(
        tenant={"en-AU": {"a": "tenant", "b": "tenant", "c": "tenant"}},
        client={"en-AU": {"a": "client", "b": "client"}},
        project={"en-AU": {"a": "project"}},
    )
    assert resolve_from(layers, ["a", "b", "c"], "en-AU", TENANT_A_ID) == {
        "a": "project",
        "b": "client",
        "c": "tenant",
    }


def test_a_missing_locale_falls_back_to_the_tenant_default() -> None:
    layers = Layers(tenant={"en-AU": {HOLD: "Hold point"}}, default_locale="en-AU")
    assert resolve_from(layers, [HOLD], "fr-FR", TENANT_A_ID) == {HOLD: "Hold point"}


def test_the_tenant_default_locale_comes_before_en_au() -> None:
    layers = Layers(
        tenant={"en-AU": {HOLD: "Hold point"}, "en-NZ": {HOLD: "Hold (NZ)"}},
        default_locale="en-NZ",
    )
    assert resolve_from(layers, [HOLD], "fr-FR", TENANT_A_ID) == {HOLD: "Hold (NZ)"}


def test_a_key_in_no_level_is_a_visible_fallback_and_logs_a_miss() -> None:
    with capture_logs() as logs:
        out = resolve_from(Layers(tenant={}), ["ghost.key"], "en-AU", TENANT_A_ID)
    assert out == {"ghost.key": "⟦ghost.key⟧"}
    assert {
        "event": "terms.miss",
        "key": "ghost.key",
        "locale": "en-AU",
        "tenant_id": str(TENANT_A_ID),
        "log_level": "warning",
    } in logs


def test_the_platform_port_serves_the_module_resolver() -> None:
    try:
        api.install()
        assert term_resolver() is api.get_api()
    finally:
        register_term_resolver(None)


# --- integration -------------------------------------------------------------------------------


@pytest.fixture
async def terms_db(tenant_db: TenantDb) -> TenantDb:
    await load(EN_AU, url=tenant_db.db.owner_url)
    return tenant_db


@pytest.fixture
async def redis_cache(redis_server: RedisServer) -> AsyncIterator[RedisTermsCache]:
    cache = RedisTermsCache.from_url(redis_server.url)
    configure_cache(cache)
    try:
        yield cache
    finally:
        configure_cache(NullTermsCache())
        await cache.aclose()


def ctx(tenant: UUID = TENANT_A_ID) -> RequestContext:
    return RequestContext(
        tenant_id=tenant, request_id=f"test-{uuid.uuid4().hex}", actor_id=ALICE_ID
    )


async def resolve_as(
    db: TenantDb,
    tenant: UUID,
    key: str = HOLD,
    *,
    client_id: UUID | None = None,
    project_id: UUID | None = None,
) -> str:
    async with db.with_tenant(tenant) as conn:
        return await resolve(
            conn, key, "en-AU", tenant_id=tenant, client_id=client_id, project_id=project_id
        )


async def override(
    db: TenantDb,
    tenant: UUID,
    value: str,
    *,
    client_id: UUID | None = None,
    project_id: UUID | None = None,
) -> None:
    async with db.with_tenant(tenant) as conn:
        await set_override(
            conn,
            tenant_id=tenant,
            key=HOLD,
            locale="en-AU",
            text=value,
            client_id=client_id,
            project_id=project_id,
            actor_id=ALICE_ID,
        )


async def test_a_rio_client_override_applies_only_on_rio_projects(
    terms_db: TenantDb, redis_cache: RedisTermsCache
) -> None:
    await override(terms_db, TENANT_A_ID, "Inspection stop", client_id=RIO_CLIENT)
    rio = await resolve_as(terms_db, TENANT_A_ID, client_id=RIO_CLIENT, project_id=RIO_PROJECT)
    other = await resolve_as(terms_db, TENANT_A_ID, project_id=OTHER_PROJECT)
    assert (rio, other) == ("Inspection stop", "Hold point")
    # A project override still beats the client's.
    await override(terms_db, TENANT_A_ID, "Rio site stop", project_id=RIO_PROJECT)
    rio = await resolve_as(terms_db, TENANT_A_ID, client_id=RIO_CLIENT, project_id=RIO_PROJECT)
    assert rio == "Rio site stop"


async def test_a_tenant_override_written_through_the_service_is_never_stale(
    terms_db: TenantDb, redis_cache: RedisTermsCache
) -> None:
    assert await resolve_as(terms_db, TENANT_A_ID) == "Hold point"  # warms the cache
    await override(terms_db, TENANT_A_ID, "Stop point")
    assert await resolve_as(terms_db, TENANT_A_ID) == "Stop point"
    await override(terms_db, TENANT_A_ID, "Stop point v2")
    assert await resolve_as(terms_db, TENANT_A_ID) == "Stop point v2"


async def test_an_uncommitted_override_is_never_cached(
    terms_db: TenantDb, redis_cache: RedisTermsCache
) -> None:
    class RollbackError(Exception):
        pass

    with pytest.raises(RollbackError):
        async with terms_db.with_tenant(TENANT_A_ID) as conn:
            await set_override(
                conn, tenant_id=TENANT_A_ID, key=HOLD, locale="en-AU", text="Never committed"
            )
            got = await resolve(conn, HOLD, "en-AU", tenant_id=TENANT_A_ID)
            assert got == "Never committed"  # the writer sees its own write
            raise RollbackError
    assert await resolve_as(terms_db, TENANT_A_ID) == "Hold point"


async def test_an_uncommitted_pack_activation_is_never_cached(
    terms_db: TenantDb, redis_cache: RedisTermsCache
) -> None:
    async with terms_db.with_tenant(TENANT_A_ID) as conn:
        pack_id = await insert_pack(conn, TENANT_A_ID, "au-mining")

    class RollbackError(Exception):
        pass

    c = ctx()
    with pytest.raises(RollbackError):
        async with use_context(c), terms_db.with_tenant(c) as conn:
            version_id = await insert_version(conn, TENANT_A_ID, pack_id, 1, "Never active")
            await activate_pack_version(
                conn, tenant_id=TENANT_A_ID, pack_id=pack_id, version_id=version_id
            )
            assert await resolve(conn, HOLD, "en-AU", tenant_id=TENANT_A_ID) == "Never active"
            raise RollbackError
    assert await resolve_as(terms_db, TENANT_A_ID) == "Hold point"


async def test_an_unreadable_cache_entry_is_a_miss(
    terms_db: TenantDb, redis_server: RedisServer, redis_cache: RedisTermsCache
) -> None:
    from redis.asyncio import Redis

    client = Redis.from_url(redis_server.url)  # pyright: ignore[reportUnknownMemberType]
    try:
        await client.set(f"t:{TENANT_A_ID}:terms:0", b"not json")
        assert await resolve_as(terms_db, TENANT_A_ID) == "Hold point"
    finally:
        await client.aclose()


async def test_tenant_b_overrides_never_reach_tenant_a(
    terms_db: TenantDb, redis_cache: RedisTermsCache
) -> None:
    await override(terms_db, TENANT_B_ID, "Acme hold")
    assert await resolve_as(terms_db, TENANT_B_ID) == "Acme hold"
    assert await resolve_as(terms_db, TENANT_A_ID) == "Hold point"
    # B's cached map is never served on A's connection.
    with pytest.raises(TenantMismatchError):
        async with terms_db.with_tenant(TENANT_A_ID) as conn:
            await resolve(conn, HOLD, "en-AU", tenant_id=TENANT_B_ID)


async def insert_pack(conn: AsyncConnection, tenant: UUID, code: str) -> UUID:
    pack_id = uuid.uuid4()
    await conn.execute(
        text("INSERT INTO term_pack (id, tenant_id, code, name) VALUES (:id, :t, :code, :code)"),
        {"id": pack_id, "t": tenant, "code": code},
    )
    return pack_id


async def insert_version(
    conn: AsyncConnection, tenant: UUID, pack_id: UUID, version: int, hold: str
) -> UUID:
    contents = json.dumps({HOLD: {"en-AU": hold}})
    version_id = uuid.uuid4()
    await conn.execute(
        text(
            "INSERT INTO term_pack_version (id, tenant_id, pack_id, version, contents,"
            " contents_sha256) VALUES (:id, :t, :p, :v, CAST(:c AS jsonb), :sha)"
        ),
        {
            "id": version_id,
            "t": tenant,
            "p": pack_id,
            "v": version,
            "c": contents,
            "sha": hashlib.sha256(contents.encode()).hexdigest(),
        },
    )
    return version_id


async def activate(db: TenantDb, tenant: UUID, pack_id: UUID, hold: str, version: int) -> None:
    c = ctx(tenant)
    async with use_context(c), db.with_tenant(c) as conn:
        version_id = await insert_version(conn, tenant, pack_id, version, hold)
        await activate_pack_version(conn, tenant_id=tenant, pack_id=pack_id, version_id=version_id)


async def test_activating_a_pack_invalidates_the_cache_through_the_outbox(
    migrated_db: FreshDb, terms_db: TenantDb, redis_cache: RedisTermsCache
) -> None:
    async with terms_db.with_tenant(TENANT_A_ID) as conn:
        pack_id = await insert_pack(conn, TENANT_A_ID, "au-mining")
    await activate(terms_db, TENANT_A_ID, pack_id, "Hold (mining v1)", 1)
    jobs = create_app_engine(EngineSettings(url=migrated_db.role_url(JOBS)))
    registry = subscribers.for_modules(["terms"])
    try:
        assert (await dispatch_batch(jobs, terms_db.engine, registry)).claimed == 1
        assert await resolve_as(terms_db, TENANT_A_ID) == "Hold (mining v1)"  # cached

        await activate(terms_db, TENANT_A_ID, pack_id, "Hold (mining v2)", 2)
        # The pack changed in Postgres, but nothing has invalidated the cache yet.
        assert await resolve_as(terms_db, TENANT_A_ID) == "Hold (mining v1)"
        assert (await dispatch_batch(jobs, terms_db.engine, registry)).claimed == 1
        assert await resolve_as(terms_db, TENANT_A_ID) == "Hold (mining v2)"
    finally:
        await jobs.dispose()
    # A tenant override still beats the market pack; tenant B never sees A's pack.
    await override(terms_db, TENANT_A_ID, "Kaefer hold")
    assert await resolve_as(terms_db, TENANT_A_ID) == "Kaefer hold"
    assert await resolve_as(terms_db, TENANT_B_ID) == "Hold point"


async def test_activating_another_packs_version_is_refused(terms_db: TenantDb) -> None:
    async with terms_db.with_tenant(TENANT_A_ID) as conn:
        first = await insert_pack(conn, TENANT_A_ID, "au-mining")
        second = await insert_pack(conn, TENANT_A_ID, "nz")
        version_id = await insert_version(conn, TENANT_A_ID, first, 1, "Hold")
    c = ctx()
    with pytest.raises(PackNotFoundError):
        async with use_context(c), terms_db.with_tenant(c) as conn:
            await activate_pack_version(
                conn, tenant_id=TENANT_A_ID, pack_id=second, version_id=version_id
            )


async def test_resolve_reads_postgres_when_redis_is_down(
    terms_db: TenantDb, redis_server: RedisServer, redis_cache: RedisTermsCache
) -> None:
    await override(terms_db, TENANT_A_ID, "Rio site stop", project_id=RIO_PROJECT)
    assert await resolve_as(terms_db, TENANT_A_ID, project_id=RIO_PROJECT) == "Rio site stop"
    redis_server.stop()
    assert await resolve_as(terms_db, TENANT_A_ID, project_id=RIO_PROJECT) == "Rio site stop"
    assert await resolve_as(terms_db, TENANT_A_ID) == "Hold point"
    # Writes still commit; the lost bump is logged and bounded by the cache TTL.
    await override(terms_db, TENANT_A_ID, "Stop point")
    assert await resolve_as(terms_db, TENANT_A_ID) == "Stop point"


async def test_bulk_resolve_returns_every_catalogue_key_with_display_text(
    terms_db: TenantDb, redis_cache: RedisTermsCache
) -> None:
    await override(terms_db, TENANT_A_ID, "Stop point")
    async with terms_db.with_tenant(TENANT_A_ID) as conn:
        everything = await bulk_resolve(conn, None, "en-AU", tenant_id=TENANT_A_ID)
        some = await bulk_resolve(conn, [HOLD, "ghost.key"], "en-AU", tenant_id=TENANT_A_ID)
    catalogue = {
        key for path in EN_AU.glob("*.json") for key in json.loads(path.read_text("utf-8"))
    }
    assert set(everything) == catalogue
    assert everything[HOLD] == "Stop point"
    assert everything["access.method.mewp"] == "MEWP"
    assert all(value and value != key for key, value in everything.items())
    assert some == {HOLD: "Stop point", "ghost.key": "⟦ghost.key⟧"}
