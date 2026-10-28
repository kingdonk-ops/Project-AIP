"""Recording a change to who holds which grants (ACCESS-04, ADR 0039).

Every write that can change a user's grants calls one of these on its ``with_tenant`` connection,
in the same transaction as the change:

- ``record_grants_changed(conn, user_ids)``: emits ``access.grants_changed`` (``None``: the
  whole tenant);
- ``record_membership_changed(conn, team_id, user_ids, change)``: emits
  ``team.membership_changed``.

Both always bump the tenant's Postgres access version (ADR 0020); when someone is affected they
also register an after-commit hook
that bumps the policy cache versions in Redis, so the instance that made the change reads the new
grants on its next check (read-your-writes). The outbox subscribers in ``events`` bump the same
versions again once the event is dispatched, for every other instance and for a lost hook. A
failing hook is logged, never raised (the change is committed).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.access.events import GRANTS_CHANGED, TEAM_MEMBERSHIP_CHANGED
from aip.modules.access.policy_cache import get_policy_cache
from aip.modules.access.repository import bump_access_version
from aip.platform.context import get_context
from aip.platform.db.session import after_commit
from aip.platform.events import Aggregate, emit

__all__ = ["record_grants_changed", "record_membership_changed"]


def _bump_after_commit(conn: AsyncConnection, tenant_id: UUID, users: list[UUID] | None) -> None:
    async def bump() -> None:
        await get_policy_cache().bump(tenant_id, users)

    after_commit(conn, bump)


async def record_grants_changed(conn: AsyncConnection, user_ids: Iterable[UUID] | None) -> None:
    """The grants of ``user_ids`` (``None``: everyone in the tenant) may have changed."""
    users = None if user_ids is None else sorted(set(user_ids))
    await bump_access_version(conn)
    if users == []:  # e.g. a role assigned to a team with no members yet: nobody to invalidate
        return
    tenant_id = get_context().tenant_id
    await emit(conn, GRANTS_CHANGED, 1, Aggregate("tenant", tenant_id), {"userIds": users})
    _bump_after_commit(conn, tenant_id, users)


async def record_membership_changed(
    conn: AsyncConnection,
    team_id: UUID,
    user_ids: Iterable[UUID],
    change: Literal["added", "removed"],
) -> None:
    """``user_ids`` joined (``added``) or left (``removed``) team ``team_id``."""
    users = sorted(set(user_ids))
    if not users:
        return
    tenant_id = get_context().tenant_id
    payload = {"teamId": team_id, "userIds": users, "change": change}
    await emit(conn, TEAM_MEMBERSHIP_CHANGED, 1, Aggregate("team", team_id), payload)
    await bump_access_version(conn)
    _bump_after_commit(conn, tenant_id, users)
