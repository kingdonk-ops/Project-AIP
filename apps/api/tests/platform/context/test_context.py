"""Unit tests for the request context (ARCH-04)."""

from __future__ import annotations

import asyncio
import dataclasses
import uuid
from typing import Any
from uuid import UUID

import anyio.to_thread
import pytest

from aip.platform.context import (
    ContextMissingError,
    RequestContext,
    get_context,
    run_with_context,
    use_context,
)
from aip.platform.jobs.context import tenant_job

T1 = UUID("00000000-0000-4000-8000-000000000001")
T2 = UUID("00000000-0000-4000-8000-000000000002")


def ctx(tenant_id: UUID = T1, **kwargs: Any) -> RequestContext:
    return RequestContext(
        tenant_id=tenant_id, request_id=kwargs.pop("request_id", "req-1"), **kwargs
    )


async def test_run_with_context_survives_await() -> None:
    async def coro() -> UUID:
        await asyncio.sleep(0.005)
        return get_context().tenant_id

    assert await run_with_context(ctx(T1), coro) == T1


async def test_run_with_context_passes_args() -> None:
    async def add(a: int, b: int) -> tuple[int, UUID]:
        return a + b, get_context().tenant_id

    assert await run_with_context(ctx(T2), add, 1, 2) == (3, T2)


def test_get_context_without_scope_raises() -> None:
    with pytest.raises(ContextMissingError):
        get_context()


async def test_gather_of_fifty_keeps_each_tenant() -> None:
    tenants = [uuid.uuid4() for _ in range(50)]

    async def coro() -> UUID:
        await asyncio.sleep(0.001)
        return get_context().tenant_id

    results = await asyncio.gather(*(run_with_context(ctx(t), coro) for t in tenants))
    assert results == tenants


async def test_context_survives_create_task_and_call_later() -> None:
    loop = asyncio.get_running_loop()
    seen: asyncio.Future[UUID] = loop.create_future()

    async def child() -> UUID:
        await asyncio.sleep(0)
        return get_context().tenant_id

    async with use_context(ctx(T1)):
        task = asyncio.create_task(child())
        loop.call_later(0.001, lambda: seen.set_result(get_context().tenant_id))
    # Scope has exited; the task and callback captured a copy when they were scheduled.
    assert await task == T1
    assert await seen == T1
    with pytest.raises(ContextMissingError):
        get_context()


async def test_context_survives_to_thread() -> None:
    def sync_dependency() -> UUID:
        return get_context().tenant_id

    async with use_context(ctx(T2)):
        assert await anyio.to_thread.run_sync(sync_dependency) == T2


def test_sync_use_context_resets_on_exit() -> None:
    with use_context(ctx(T1)):
        assert get_context().tenant_id == T1
        with use_context(ctx(T2)):
            assert get_context().tenant_id == T2
        assert get_context().tenant_id == T1
    with pytest.raises(ContextMissingError):
        get_context()


def test_use_context_resets_on_exception() -> None:
    with pytest.raises(RuntimeError), use_context(ctx(T1)):
        raise RuntimeError("boom")
    with pytest.raises(ContextMissingError):
        get_context()


def test_request_context_is_frozen_and_validated() -> None:
    c = ctx(T1, project_id=None, actor_id=None, asset_path_scope=("site_a.unit_1",))
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.tenant_id = T2  # type: ignore[misc]
    with pytest.raises(ValueError):
        ctx(T1, asset_path_scope=("not a valid; ltree",))
    with pytest.raises(ValueError):
        ctx(T1, request_id="")


async def test_tenant_job_runs_inside_context() -> None:
    @tenant_job
    async def handler(**payload: Any) -> UUID:
        return get_context().tenant_id

    assert await handler(tenant_id=str(T1)) == T1


async def test_tenant_job_carries_actor_and_request_id() -> None:
    actor = uuid.uuid4()

    @tenant_job
    async def handler(tenant_id: str, actor_id: str, request_id: str) -> RequestContext:
        return get_context()

    c = await handler(tenant_id=str(T1), actor_id=str(actor), request_id="req-xyz")
    assert (c.tenant_id, c.actor_id, c.request_id) == (T1, actor, "req-xyz")


async def test_tenant_job_without_tenant_raises_before_body() -> None:
    ran = False

    @tenant_job
    async def handler(**payload: Any) -> None:
        nonlocal ran
        ran = True

    with pytest.raises(ContextMissingError):
        await handler(**{})
    assert ran is False


def test_tenant_job_wraps_sync_handlers() -> None:
    @tenant_job
    def handler(**payload: Any) -> UUID:
        return get_context().tenant_id

    assert handler(tenant_id=str(T2)) == T2
    with pytest.raises(ContextMissingError):
        handler()
