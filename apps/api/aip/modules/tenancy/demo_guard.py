"""The demo start-up guard (OPS-11, ADR 0007): real customer data never lands on the Coolify demo.

With ``AIP_ENV=demo`` the API calls ``assert_demo_has_no_real_customers`` at start-up; if any live
tenant has ``is_real_customer`` set, it raises ``RealDataInDemoError`` and the API does not start.
The check reads through ``tenancy_has_real_customer()`` (SECURITY DEFINER, one boolean) because no
tenant is bound at start-up. Without a database it fails closed: the guard cannot prove the demo
is clean, so the API refuses to start.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.db.engine import DATABASE_URL_ENV
from aip.platform.db.session import before_tenant

__all__ = ["DEMO_ENV", "RealDataInDemoError", "assert_demo_has_no_real_customers"]

DEMO_ENV = "demo"
_CHECK = text("SELECT tenancy_has_real_customer()")

Connect = Callable[[], AbstractAsyncContextManager[AsyncConnection]]


class RealDataInDemoError(RuntimeError):
    """A tenant with real customer data exists in a demo deployment."""


async def assert_demo_has_no_real_customers(connect: Connect | None = None) -> None:
    if connect is None:
        if not os.environ.get(DATABASE_URL_ENV):
            raise RealDataInDemoError(
                f"{DATABASE_URL_ENV} is not set: cannot prove the demo holds no real customer data"
            )
        connect = before_tenant
    async with connect() as conn:
        found = bool((await conn.execute(_CHECK)).scalar_one())
    if found:
        raise RealDataInDemoError(
            "a tenant marked is_real_customer exists; real customer data must never run on the "
            "demo (ADR 0007)"
        )
