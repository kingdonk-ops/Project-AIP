"""Business logic for terms: the resolver and override writes (TERMS-02).

Resolution checks the most specific level first: project override, client override, tenant
override, the tenant's active market pack versions, then the platform default. Locales fall back
from the requested locale to the tenant default (``locale_settings``) and then ``en-AU``; a text in
a better locale beats a more specific level in a worse one. A key found nowhere resolves to the
visible ``⟦key⟧`` and logs ``terms.miss``, so a raw key or internal code never reaches a user.

The merged maps are cached per tenant (:mod:`.cache`). Override writes made here bump the cache
version after commit; until then, resolves on the writing connection bypass the cache so they
neither see stale text nor cache uncommitted text. Resolves in this process wait for pending bumps
of their tenant, so a write followed by a resolve never reads the old version.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.events import Aggregate, emit

from . import repository
from .cache import get_cache
from .events import TERMS_PACK_ACTIVATED
from .repository import OverrideLevel, Texts

__all__ = [
    "FALLBACK_LOCALE",
    "Layers",
    "PackNotFoundError",
    "TenantMismatchError",
    "activate_pack_version",
    "bulk_resolve",
    "locale_chain",
    "missing",
    "pick",
    "resolve",
    "set_override",
]

logger = structlog.stdlib.get_logger(__name__)

FALLBACK_LOCALE = "en-AU"
_DIRTY = "aip.terms.dirty_tenants"  # conn.info: tenants with uncommitted override writes
_pending_bumps: dict[UUID, set[asyncio.Task[None]]] = {}


class TenantMismatchError(ValueError):
    """``tenant_id`` is not the tenant the connection is bound to (the cache is keyed by it)."""


class PackNotFoundError(LookupError):
    """The pack does not exist for this tenant (or is deleted)."""


@dataclass(frozen=True, slots=True)
class Layers:
    """Everything one resolve needs, most specific level first in :meth:`levels`."""

    tenant: Texts
    default_locale: str | None = None
    client: Texts = field(default_factory=dict[str, dict[str, str]])
    project: Texts = field(default_factory=dict[str, dict[str, str]])

    def levels(self) -> tuple[Texts, Texts, Texts]:
        return (self.project, self.client, self.tenant)


def locale_chain(requested: str, tenant_default: str | None) -> list[str]:
    """``requested``, then the tenant default, then ``en-AU``, without repeats."""
    chain = [requested, tenant_default or FALLBACK_LOCALE, FALLBACK_LOCALE]
    return list(dict.fromkeys(chain))


def missing(key: str) -> str:
    """The visible fallback for a key found nowhere."""
    return f"⟦{key}⟧"


def pick(layers: Layers, key: str, chain: Iterable[str]) -> str | None:
    for locale in chain:
        for texts in layers.levels():
            found = texts.get(locale, {}).get(key)
            if found is not None:
                return found
    return None


def merge(base: Texts, *overlays: Texts) -> Texts:
    merged = {locale: dict(texts) for locale, texts in base.items()}
    for overlay in overlays:
        for locale, texts in overlay.items():
            merged.setdefault(locale, {}).update(texts)
    return merged


def pack_texts(contents: Iterable[Mapping[str, Any]]) -> Texts:
    """Pack contents ``{key: {locale: text}}`` as ``{locale: {key: text}}`` (later packs win)."""
    texts: Texts = {}
    for pack in contents:
        for key, by_locale in pack.items():
            if not isinstance(by_locale, Mapping):
                continue
            for locale, value in by_locale.items():  # pyright: ignore[reportUnknownVariableType]
                if isinstance(value, str) and value:
                    texts.setdefault(str(locale), {})[key] = value  # pyright: ignore[reportUnknownArgumentType]
    return texts


# --- loading, with the cache -------------------------------------------------------------------


async def _load_tenant(conn: AsyncConnection, tenant_id: UUID) -> dict[str, Any]:
    tenant = merge(
        await repository.defaults(conn),
        pack_texts(await repository.active_pack_contents(conn, tenant_id)),
        await repository.overrides(conn, tenant_id, "tenant"),
    )
    return {"locale": await repository.tenant_default_locale(conn, tenant_id), "texts": tenant}


async def _cached(
    conn: AsyncConnection,
    tenant_id: UUID,
    version: int | None,
    scope: str,
    load: Any,
) -> Any:
    cache = get_cache()
    if version is not None:
        hit = await cache.get(tenant_id, version, scope)
        if hit is not None:
            return hit
    value = await load()
    if version is not None:
        await cache.put(tenant_id, version, scope, value)
    return value


async def _layers(
    conn: AsyncConnection, tenant_id: UUID, client_id: UUID | None, project_id: UUID | None
) -> Layers:
    if await repository.bound_tenant(conn) != tenant_id:
        raise TenantMismatchError("tenant_id differs from the connection's with_tenant tenant")
    pending = _pending_bumps.get(tenant_id)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    dirty: set[UUID] = conn.info.get(_DIRTY, set())
    version = None if tenant_id in dirty else await get_cache().version(tenant_id)

    tenant = await _cached(conn, tenant_id, version, "", lambda: _load_tenant(conn, tenant_id))
    client: Texts = {}
    if client_id is not None:
        client = await _cached(
            conn,
            tenant_id,
            version,
            f":client:{client_id}",
            lambda: repository.overrides(conn, tenant_id, "client", client_id),
        )
    project: Texts = {}
    if project_id is not None:
        project = await _cached(
            conn,
            tenant_id,
            version,
            f":project:{project_id}",
            lambda: repository.overrides(conn, tenant_id, "project", project_id),
        )
    return Layers(
        tenant=tenant["texts"], default_locale=tenant["locale"], client=client, project=project
    )


def resolve_from(
    layers: Layers, keys: Iterable[str], locale: str, tenant_id: UUID
) -> dict[str, str]:
    chain = locale_chain(locale, layers.default_locale)
    out: dict[str, str] = {}
    for key in keys:
        found = pick(layers, key, chain)
        if found is None:
            logger.warning("terms.miss", key=key, locale=locale, tenant_id=str(tenant_id))
            found = missing(key)
        out[key] = found
    return out


async def resolve(
    conn: AsyncConnection,
    key: str,
    locale: str,
    *,
    tenant_id: UUID,
    client_id: UUID | None = None,
    project_id: UUID | None = None,
) -> str:
    """The text of ``key`` for this tenant, client and project (see the module docstring)."""
    layers = await _layers(conn, tenant_id, client_id, project_id)
    return resolve_from(layers, [key], locale, tenant_id)[key]


async def bulk_resolve(
    conn: AsyncConnection,
    keys: Iterable[str] | None,
    locale: str,
    *,
    tenant_id: UUID,
    client_id: UUID | None = None,
    project_id: UUID | None = None,
) -> dict[str, str]:
    """Resolve many keys at once (every catalogue key when ``keys`` is ``None``), for UI bundles."""
    layers = await _layers(conn, tenant_id, client_id, project_id)
    if keys is None:
        keys = sorted({key for texts in layers.tenant.values() for key in texts})
    return resolve_from(layers, keys, locale, tenant_id)


# --- writes ------------------------------------------------------------------------------------


def _bump_after_commit(conn: AsyncConnection, tenant_id: UUID) -> None:
    dirty: set[UUID] = conn.info.setdefault(_DIRTY, set())
    if tenant_id in dirty:
        return  # already scheduled for this transaction
    dirty.add(tenant_id)
    loop = asyncio.get_running_loop()
    sync_conn = conn.sync_connection
    assert sync_conn is not None

    fired = False  # commit and rollback listeners are both "once": whichever runs first wins

    def _after_commit(_conn: object) -> None:
        nonlocal fired
        if fired:
            return
        fired = True
        dirty.discard(tenant_id)
        task = loop.create_task(get_cache().bump(tenant_id))
        tasks = _pending_bumps.setdefault(tenant_id, set())
        tasks.add(task)
        task.add_done_callback(lambda t: _bump_done(tenant_id, t))

    def _after_rollback(_conn: object) -> None:
        nonlocal fired
        if fired:
            return
        fired = True
        dirty.discard(tenant_id)

    event.listen(sync_conn, "commit", _after_commit, once=True)
    event.listen(sync_conn, "rollback", _after_rollback, once=True)


def _bump_done(tenant_id: UUID, task: asyncio.Task[None]) -> None:
    tasks = _pending_bumps.get(tenant_id)
    if tasks is not None:
        tasks.discard(task)
        if not tasks:
            _pending_bumps.pop(tenant_id, None)
    if not task.cancelled() and task.exception() is not None:
        # The cache TTL still bounds how long the old text can be served.
        logger.warning(
            "terms.cache_bump_failed", tenant_id=str(tenant_id), error=repr(task.exception())
        )


async def set_override(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    key: str,
    locale: str,
    text: str,
    client_id: UUID | None = None,
    project_id: UUID | None = None,
    actor_id: UUID | None = None,
) -> UUID:
    """Create or replace the override of ``key`` in ``locale`` at the most specific given level.

    The cache is invalidated once the caller's transaction commits.
    """
    if client_id is not None and project_id is not None:
        raise ValueError("an override is for a client or a project, not both")
    level: OverrideLevel = (
        "project" if project_id is not None else "client" if client_id is not None else "tenant"
    )
    override_id = await repository.upsert_override(
        conn,
        tenant_id=tenant_id,
        level=level,
        client_id=client_id,
        project_id=project_id,
        key=key,
        locale=locale,
        text_=text,
        actor_id=actor_id,
    )
    _bump_after_commit(conn, tenant_id)
    return override_id


async def activate_pack_version(
    conn: AsyncConnection, *, tenant_id: UUID, pack_id: UUID, version_id: UUID
) -> None:
    """Make ``version_id`` the pack's active version and emit ``terms.pack.activated``.

    The outbox subscriber invalidates the cache once the event is delivered (after commit).
    Needs a request context (``emit`` takes tenant and actor from it).
    """
    row = await repository.pack_version(conn, tenant_id=tenant_id, version_id=version_id)
    if row is None or row.pack_id != pack_id:
        raise PackNotFoundError(f"pack {pack_id} has no version {version_id}")
    if not await repository.set_active_version(
        conn, tenant_id=tenant_id, pack_id=pack_id, version_id=version_id
    ):
        raise PackNotFoundError(f"pack {pack_id} not found")
    await emit(
        conn,
        TERMS_PACK_ACTIVATED,
        1,
        Aggregate("term_pack", pack_id),
        {"pack_id": pack_id, "version_id": version_id, "version": row.version, "code": row.code},
    )
