"""``EntitlementService``: every entitlement decision and change (ENT-01 step 5, ADR 0008/0023).

Reads:

- ``check(tenant_id, "feature.x", project_id=None) -> Decision(allowed, source)``;
- ``check_limit(tenant_id, "limit.x", requested_total) -> LimitDecision``. A ``WARN`` or
  ``OVERAGE`` limit that is exceeded is allowed and recorded in the month's ``tenant_usage``
  (``over_limit``), for ENT-02's export;
- ``check_seat(conn, tenant_id, user_class)``: whether one more active user of that class fits
  (identity calls it on activation, on its own connection);
- ``list(tenant_id)`` and ``plan_and_usage(tenant_id)``.

Caching: decisions resolve from a per-tenant snapshot (subscription and overrides) held in process
for 60 seconds under a TENANCY-02 key that includes the tenant's ``entitlement_version``. Each
check reads the version first (one indexed row), so a change made by any process applies at once
(ADR 0023 point 3), and a write here also drops the cached snapshot immediately. Expiry is
evaluated at every check against the injected ``Clock``, so a cached snapshot never revives an
expired override.

Writes (``put_subscription``, ``add_override``, ``remove_override``, ``sweep_expired_overrides``)
run in one ``with_tenant`` transaction for the target tenant, bump ``entitlement_version`` and
insert ``tenant.entitlements_changed`` in the same transaction. An operator acts for another
tenant, so the request context is re-bound to that tenant for the transaction (the actor stays the
operator); outside a request (the CLI) a context without an actor is used.
"""

from __future__ import annotations

import dataclasses
import json
import math
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.tenancy.entitlements.plans import (
    ContractRefRequiredError,
    PlanRegistry,
    check_contract_ref,
    default_registry,
)
from aip.modules.tenancy.entitlements.resolve import (
    InvalidEntitlementKey,
    LimitDecision,
    OverrideView,
    Resolution,
    Source,
    SubscriptionView,
    check_key,
    decide_limit,
    resolve,
)
from aip.modules.tenancy.entitlements.usage import (
    DB_ESTIMATE_METHOD,
    UsageSource,
    collect_usage,
    estimate_db_bytes,
)
from aip.modules.tenancy.events import TENANT_ENTITLEMENTS_CHANGED
from aip.modules.tenancy.repository import load_tenant
from aip.modules.tenancy.schemas import (
    DbEstimate,
    FeatureOut,
    LimitOut,
    OverrideCreate,
    OverrideOut,
    PlanAndUsage,
    SubscriptionOut,
    SubscriptionPut,
)
from aip.platform.context import (
    ContextMissingError,
    RequestContext,
    get_context,
    new_request_id,
    use_context,
)
from aip.platform.db.errors import NotFoundError
from aip.platform.db.session import with_tenant
from aip.platform.events import Aggregate, emit
from aip.platform.http import DomainError
from aip.platform.tenant_keys import redis_key

__all__ = [
    "CACHE_TTL_S",
    "Clock",
    "Decision",
    "EntitlementService",
    "ScopeToggleProvider",
    "clear_toggle_providers",
    "month_start",
    "register_toggle_provider",
    "utc_now",
]

CACHE_TTL_S = 60.0
_GB = 1024**3

Clock = Callable[[], datetime]
TenantConnect = Callable[[UUID], AbstractAsyncContextManager[AsyncConnection]]


def utc_now() -> datetime:
    return datetime.now(UTC)


def month_start(day: date) -> date:
    return day.replace(day=1)


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    source: Source


class ScopeToggleProvider(Protocol):
    """Site/project feature toggles; a toggle can only switch a feature off (projects registers)."""

    async def toggles(
        self, conn: AsyncConnection, tenant_id: UUID, project_id: UUID
    ) -> Mapping[str, bool]: ...


_toggle_providers: list[ScopeToggleProvider] = []


def register_toggle_provider(provider: ScopeToggleProvider) -> None:
    if provider not in _toggle_providers:
        _toggle_providers.append(provider)


def clear_toggle_providers() -> None:
    """Forget every registered provider (tests)."""
    _toggle_providers.clear()


@dataclass(frozen=True, slots=True)
class _Snapshot:
    subscription: SubscriptionView | None
    overrides: tuple[OverrideView, ...]


_VERSION = text(
    "SELECT entitlement_version FROM tenant_subscription"
    " WHERE tenant_id = :tenant_id AND deleted_at IS NULL"
)
_SUBSCRIPTION = text(
    """
    SELECT tenant_id, plan_code, plan_version, term, status, starts_on, ends_on, renewal_date,
           seat_limits, storage_gb, add_ons, contract_ref, entitlement_version
      FROM tenant_subscription
     WHERE tenant_id = :tenant_id AND deleted_at IS NULL
    """
)
_OVERRIDES = text(
    """
    SELECT id, key, value, reason, created_at, expires_at, created_by
      FROM tenant_entitlement_override
     WHERE tenant_id = :tenant_id AND deleted_at IS NULL
     ORDER BY created_at, id
    """
)
_BUMP = text(
    """
    UPDATE tenant_subscription
       SET entitlement_version = entitlement_version + 1, updated_at = now()
     WHERE tenant_id = :tenant_id AND deleted_at IS NULL
    RETURNING entitlement_version
    """
)
_UPSERT_SUBSCRIPTION = text(
    """
    INSERT INTO tenant_subscription (
        id, tenant_id, plan_code, plan_version, term, starts_on, ends_on, renewal_date,
        seat_limits, storage_gb, add_ons, contract_ref, status, updated_by)
    VALUES (
        :id, :tenant_id, :plan_code, :plan_version, :term, :starts_on, :ends_on, :renewal_date,
        CAST(:seat_limits AS jsonb), :storage_gb, :add_ons, :contract_ref, :status, :updated_by)
    ON CONFLICT (tenant_id) DO UPDATE SET
        plan_code = EXCLUDED.plan_code,
        plan_version = EXCLUDED.plan_version,
        term = EXCLUDED.term,
        starts_on = EXCLUDED.starts_on,
        ends_on = EXCLUDED.ends_on,
        renewal_date = EXCLUDED.renewal_date,
        seat_limits = EXCLUDED.seat_limits,
        storage_gb = EXCLUDED.storage_gb,
        add_ons = EXCLUDED.add_ons,
        contract_ref = EXCLUDED.contract_ref,
        status = EXCLUDED.status,
        updated_by = EXCLUDED.updated_by,
        entitlement_version = tenant_subscription.entitlement_version + 1,
        deleted_at = NULL,
        updated_at = now()
    RETURNING entitlement_version
    """
)
_INSERT_OVERRIDE = text(
    """
    INSERT INTO tenant_entitlement_override
        (id, tenant_id, key, value, reason, expires_at, created_by)
    VALUES (:id, :tenant_id, :key, CAST(:value AS jsonb), :reason, :expires_at, :created_by)
    RETURNING id, key, value, reason, created_at, expires_at, created_by
    """
)
_REMOVE_OVERRIDE = text(
    """
    UPDATE tenant_entitlement_override SET deleted_at = now(), updated_at = now()
     WHERE id = :id AND tenant_id = :tenant_id AND deleted_at IS NULL
    RETURNING id, key, value, reason, created_at, expires_at, created_by
    """
)
_EXPIRE_OVERRIDES = text(
    """
    UPDATE tenant_entitlement_override SET deleted_at = now(), updated_at = now()
     WHERE tenant_id = :tenant_id AND deleted_at IS NULL AND expires_at <= :now
    RETURNING id, key, value, reason, created_at, expires_at, created_by
    """
)
_RECORD_OVER_LIMIT = text(
    """
    INSERT INTO tenant_usage (id, tenant_id, period, over_limit)
    VALUES (:id, :tenant_id, :period, jsonb_build_object(CAST(:key AS text), CAST(:entry AS jsonb)))
    ON CONFLICT (tenant_id, period) DO UPDATE SET
        over_limit = tenant_usage.over_limit || jsonb_build_object(CAST(:key AS text),
            CASE WHEN coalesce(
                    (tenant_usage.over_limit -> CAST(:key AS text) ->> 'peak')::bigint, -1)
                      >= CAST(:peak AS bigint)
                 THEN tenant_usage.over_limit -> CAST(:key AS text)
                 ELSE CAST(:entry AS jsonb) END),
        updated_at = now()
    """
)
_UPSERT_USAGE = text(
    """
    INSERT INTO tenant_usage (
        id, tenant_id, period, active_users, storage_bytes, jobs_count, ai_spend_cents,
        db_bytes_est, db_estimate_method, db_estimated_at, captured_at)
    VALUES (
        :id, :tenant_id, :period, CAST(:active_users AS jsonb), :storage_bytes, :jobs_count,
        :ai_spend_cents, :db_bytes_est, :db_estimate_method, :db_estimated_at, :captured_at)
    ON CONFLICT (tenant_id, period) DO UPDATE SET
        active_users = EXCLUDED.active_users,
        storage_bytes = EXCLUDED.storage_bytes,
        jobs_count = EXCLUDED.jobs_count,
        ai_spend_cents = EXCLUDED.ai_spend_cents,
        db_bytes_est = coalesce(EXCLUDED.db_bytes_est, tenant_usage.db_bytes_est),
        db_estimate_method = coalesce(EXCLUDED.db_estimate_method, tenant_usage.db_estimate_method),
        db_estimated_at = coalesce(EXCLUDED.db_estimated_at, tenant_usage.db_estimated_at),
        captured_at = EXCLUDED.captured_at,
        deleted_at = NULL,
        updated_at = now()
    """
)
_LATEST_USAGE = text(
    """
    SELECT period, active_users, storage_bytes
      FROM tenant_usage
     WHERE tenant_id = :tenant_id AND deleted_at IS NULL
     ORDER BY period DESC
     LIMIT 1
    """
)
# The estimate runs weekly and at month end, so the newest month may not have one yet.
_LATEST_DB_ESTIMATE = text(
    """
    SELECT db_bytes_est, db_estimate_method, db_estimated_at
      FROM tenant_usage
     WHERE tenant_id = :tenant_id AND deleted_at IS NULL AND db_bytes_est IS NOT NULL
     ORDER BY period DESC
     LIMIT 1
    """
)


def _jsonb(value: Any) -> Any:
    """asyncpg returns jsonb as text through ``text()`` queries."""
    return json.loads(value) if isinstance(value, str) else value


def _subscription(row: RowMapping) -> SubscriptionView:
    return SubscriptionView(
        tenant_id=row["tenant_id"],
        plan_code=row["plan_code"],
        plan_version=row["plan_version"],
        term=row["term"],
        status=row["status"],
        starts_on=row["starts_on"],
        ends_on=row["ends_on"],
        renewal_date=row["renewal_date"],
        seat_limits=dict(_jsonb(row["seat_limits"]) or {}),
        storage_gb=row["storage_gb"],
        add_ons=tuple(row["add_ons"] or ()),
        contract_ref=row["contract_ref"],
        entitlement_version=row["entitlement_version"],
    )


def _override(row: RowMapping) -> OverrideView:
    return OverrideView(
        id=row["id"],
        key=row["key"],
        value=_jsonb(row["value"]),
        reason=row["reason"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        created_by=row["created_by"],
    )


def _subscription_out(view: SubscriptionView) -> SubscriptionOut:
    return SubscriptionOut.model_validate(
        {
            **dataclasses.asdict(view),
            "seat_limits": dict(view.seat_limits),
            "add_ons": list(view.add_ons),
        }
    )


def _override_out(view: OverrideView) -> OverrideOut:
    return OverrideOut(
        id=view.id,
        key=view.key,
        value=view.value,
        reason=view.reason,
        expires_at=view.expires_at,
        created_at=view.created_at,
    )


def _check_override_value(kind: str, value: bool | int | None) -> None:
    if kind == "feature" and not isinstance(value, bool):
        raise DomainError(
            422, "INVALID_OVERRIDE_VALUE", detail="feature overrides are true or false"
        )
    if kind == "limit" and isinstance(value, bool):
        raise DomainError(
            422, "INVALID_OVERRIDE_VALUE", detail="limit overrides are a count or null"
        )


class _TtlCache:
    """A small in-process TTL map; time comes from the service's clock."""

    def __init__(self, ttl_s: float, clock: Clock) -> None:
        self._ttl_s = ttl_s
        self._clock = clock
        self._items: dict[str, tuple[float, _Snapshot]] = {}

    def get(self, key: str) -> _Snapshot | None:
        item = self._items.get(key)
        if item is None:
            return None
        if item[0] <= self._clock().timestamp():
            del self._items[key]
            return None
        return item[1]

    def put(self, key: str, value: _Snapshot) -> None:
        self._items[key] = (self._clock().timestamp() + self._ttl_s, value)

    def drop_tenant(self, tenant_id: UUID) -> None:
        prefix = redis_key(tenant_id, "entitlements")
        for key in [k for k in self._items if k == prefix or k.startswith(prefix + ":")]:
            del self._items[key]


class EntitlementService:
    def __init__(
        self,
        *,
        connect: TenantConnect = with_tenant,
        clock: Clock = utc_now,
        registry: PlanRegistry | None = None,
        cache_ttl_s: float = CACHE_TTL_S,
        toggle_providers: Sequence[ScopeToggleProvider] | None = None,
        usage_sources: tuple[UsageSource, ...] | None = None,
    ) -> None:
        self._connect = connect
        self.clock = clock
        self.registry = registry or default_registry()
        self._cache = _TtlCache(cache_ttl_s, lambda: self.clock())
        self._toggle_providers = toggle_providers
        self._usage_sources = usage_sources
        self.loads = 0  # snapshot loads from the database (tests watch the cache with it)

    # --- reads --------------------------------------------------------------------------------

    async def _snapshot(self, conn: AsyncConnection, tenant_id: UUID) -> _Snapshot:
        version = (await conn.execute(_VERSION, {"tenant_id": tenant_id})).scalar_one_or_none()
        key = redis_key(tenant_id, "entitlements", f"v{version or 0}")
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        self.loads += 1
        row = (await conn.execute(_SUBSCRIPTION, {"tenant_id": tenant_id})).mappings().first()
        rows = (await conn.execute(_OVERRIDES, {"tenant_id": tenant_id})).mappings().all()
        snapshot = _Snapshot(
            subscription=None if row is None else _subscription(row),
            overrides=tuple(_override(r) for r in rows),
        )
        self._cache.drop_tenant(tenant_id)  # older versions are dead
        self._cache.put(key, snapshot)
        return snapshot

    async def _toggles(
        self, conn: AsyncConnection, tenant_id: UUID, project_id: UUID | None
    ) -> dict[str, bool]:
        if project_id is None:
            return {}
        merged: dict[str, bool] = {}
        providers = _toggle_providers if self._toggle_providers is None else self._toggle_providers
        for provider in providers:
            for key, on in (await provider.toggles(conn, tenant_id, project_id)).items():
                merged[key] = merged.get(key, True) and on  # any provider can switch off
        return merged

    def _resolve(
        self, key: str, snapshot: _Snapshot, toggles: Mapping[str, bool], now: datetime
    ) -> Resolution:
        sub = snapshot.subscription
        plan = None if sub is None else self.registry.plan(sub.plan_code)
        add_ons = [] if sub is None else [a for c in sub.add_ons if (a := self.registry.add_on(c))]
        return resolve(
            key,
            subscription=sub,
            plan=plan,
            add_ons=add_ons,
            overrides=snapshot.overrides,
            toggles=toggles,
            now=now,
        )

    async def check(
        self, tenant_id: UUID, feature_key: str, *, project_id: UUID | None = None
    ) -> Decision:
        if check_key(feature_key) != "feature":
            raise InvalidEntitlementKey(feature_key)
        async with self._connect(tenant_id) as conn:
            snapshot = await self._snapshot(conn, tenant_id)
            toggles = await self._toggles(conn, tenant_id, project_id)
        result = self._resolve(feature_key, snapshot, toggles, self.clock())
        return Decision(bool(result.value), result.source)

    async def _limit_on(
        self, conn: AsyncConnection, tenant_id: UUID, limit_key: str, requested_total: int
    ) -> LimitDecision:
        if check_key(limit_key) != "limit":
            raise InvalidEntitlementKey(limit_key)
        now = self.clock()
        snapshot = await self._snapshot(conn, tenant_id)
        decision = decide_limit(self._resolve(limit_key, snapshot, {}, now), requested_total)
        if decision.recorded:
            entry = {"action": decision.action, "limit": decision.limit, "peak": requested_total}
            await conn.execute(
                _RECORD_OVER_LIMIT,
                {
                    "id": uuid4(),
                    "tenant_id": tenant_id,
                    "period": month_start(now.date()),
                    "key": limit_key,
                    "entry": json.dumps(entry),
                    "peak": requested_total,
                },
            )
        return decision

    async def check_limit(
        self, tenant_id: UUID, limit_key: str, requested_total: int
    ) -> LimitDecision:
        async with self._connect(tenant_id) as conn:
            return await self._limit_on(conn, tenant_id, limit_key, requested_total)

    async def check_seat(
        self, conn: AsyncConnection, tenant_id: UUID, user_class: str
    ) -> LimitDecision:
        """Whether one more active ``user_class`` user fits (staff and field share full seats)."""
        figures = await collect_usage(conn, tenant_id, self._usage_sources)
        users = figures.active_users
        if user_class == "portal":
            key, current = "limit.seats.portal", users.get("portal", 0)
        else:
            key = "limit.seats.full"
            current = users.get("staff", 0) + users.get("field", 0) + users.get("full", 0)
        return await self._limit_on(conn, tenant_id, key, current + 1)

    async def list(self, tenant_id: UUID) -> list[tuple[str, Resolution]]:
        """Every feature and limit key the plans know, resolved for ``tenant_id``."""
        async with self._connect(tenant_id) as conn:
            snapshot = await self._snapshot(conn, tenant_id)
        now = self.clock()
        keys = [*self.registry.feature_keys(), *self.registry.limit_keys()]
        return [(key, self._resolve(key, snapshot, {}, now)) for key in keys]

    async def plan_and_usage(self, tenant_id: UUID) -> PlanAndUsage:
        async with self._connect(tenant_id) as conn:
            snapshot = await self._snapshot(conn, tenant_id)
            usage = (await conn.execute(_LATEST_USAGE, {"tenant_id": tenant_id})).mappings().first()
            db_row = (
                (await conn.execute(_LATEST_DB_ESTIMATE, {"tenant_id": tenant_id}))
                .mappings()
                .first()
            )
        now = self.clock()
        used = _used_by_key(usage, None if db_row is None else db_row["db_bytes_est"])
        features = [
            FeatureOut(key=key, enabled=bool(r.value), source=r.source)
            for key in self.registry.feature_keys()
            for r in [self._resolve(key, snapshot, {}, now)]
        ]
        limits = [
            LimitOut(
                key=key,
                limit=None if r.value is None else int(r.value),
                used=used.get(key),
                action=r.action or "BLOCK",
                source=r.source,
            )
            for key in self.registry.limit_keys()
            for r in [self._resolve(key, snapshot, {}, now)]
        ]
        sub = snapshot.subscription
        estimate = None
        if db_row is not None:
            estimate = DbEstimate(
                bytes=db_row["db_bytes_est"],
                method=db_row["db_estimate_method"] or DB_ESTIMATE_METHOD,
                captured_at=db_row["db_estimated_at"],
            )
        return PlanAndUsage(
            plan=None if sub is None else sub.plan_code,
            plan_version=None if sub is None else sub.plan_version,
            term=None if sub is None else sub.term,  # pyright: ignore[reportArgumentType]
            status=None if sub is None else sub.status,  # pyright: ignore[reportArgumentType]
            renewal_date=None if sub is None else sub.renewal_date,
            contract_ref=None if sub is None else sub.contract_ref,
            usage_period=None if usage is None else usage["period"],
            features=features,
            limits=limits,
            db_estimate=estimate,
        )

    # --- writes -------------------------------------------------------------------------------

    @asynccontextmanager
    async def _for_tenant(self, tenant_id: UUID) -> AsyncIterator[AsyncConnection]:
        """A transaction for ``tenant_id`` with the request context re-bound to it."""
        try:
            ctx = dataclasses.replace(
                get_context(),
                tenant_id=tenant_id,
                project_id=None,
                tenant_slug=None,
                region_code=None,
                asset_path_scope=(),
            )
        except ContextMissingError:
            ctx = RequestContext(tenant_id=tenant_id, request_id=new_request_id())
        try:
            with use_context(ctx):
                async with self._connect(tenant_id) as conn:
                    if await load_tenant(conn, tenant_id) is None:
                        raise NotFoundError(f"tenant {tenant_id}")
                    yield conn
        finally:
            self._cache.drop_tenant(tenant_id)

    async def _emit(
        self,
        conn: AsyncConnection,
        tenant_id: UUID,
        version: int,
        change: str,
        **fields: Any,
    ) -> None:
        payload = {"tenantId": tenant_id, "entitlementVersion": version, "change": change, **fields}
        await emit(conn, TENANT_ENTITLEMENTS_CHANGED, 1, Aggregate("tenant", tenant_id), payload)

    async def _bump(self, conn: AsyncConnection, tenant_id: UUID) -> int:
        """The new ``entitlement_version``; 0 when the tenant has no subscription to version."""
        return (await conn.execute(_BUMP, {"tenant_id": tenant_id})).scalar_one_or_none() or 0

    async def put_subscription(self, tenant_id: UUID, body: SubscriptionPut) -> SubscriptionOut:
        plan = self.registry.plan(body.plan_code)
        if plan is None:
            raise DomainError(422, "UNKNOWN_PLAN", key=body.plan_code)
        if body.plan_version not in (None, plan.version):
            raise DomainError(422, "UNKNOWN_PLAN_VERSION", key=body.plan_code)
        unknown = sorted(set(body.add_ons) - set(self.registry.add_ons))
        if unknown:
            raise DomainError(422, "UNKNOWN_ADD_ON", key=", ".join(unknown))
        try:
            check_contract_ref(body.term, body.contract_ref)
        except ContractRefRequiredError:
            raise DomainError(422, "CONTRACT_REF_REQUIRED") from None
        if body.ends_on is not None and body.ends_on < body.starts_on:
            raise DomainError(422, "INVALID_DATES")
        actor = _actor()
        async with self._for_tenant(tenant_id) as conn:
            row = (await conn.execute(_SUBSCRIPTION, {"tenant_id": tenant_id})).mappings().first()
            before = None if row is None else _subscription_out(_subscription(row))
            version = (
                await conn.execute(
                    _UPSERT_SUBSCRIPTION,
                    {
                        "id": uuid4(),
                        "tenant_id": tenant_id,
                        "plan_code": plan.code,
                        "plan_version": body.plan_version or plan.version,
                        "term": body.term,
                        "starts_on": body.starts_on,
                        "ends_on": body.ends_on,
                        "renewal_date": body.renewal_date,
                        "seat_limits": json.dumps(body.seat_limits),
                        "storage_gb": body.storage_gb,
                        "add_ons": sorted(set(body.add_ons)),
                        "contract_ref": body.contract_ref,
                        "status": body.status,
                        "updated_by": actor,
                    },
                )
            ).scalar_one()
            row = (await conn.execute(_SUBSCRIPTION, {"tenant_id": tenant_id})).mappings().one()
            after = _subscription_out(_subscription(row))
            await self._emit(
                conn,
                tenant_id,
                version,
                "subscription",
                before=None if before is None else before.model_dump(mode="json", by_alias=True),
                after=after.model_dump(mode="json", by_alias=True),
                reason=body.reason,
            )
        return after

    async def add_override(self, tenant_id: UUID, body: OverrideCreate) -> OverrideOut:
        try:
            kind = check_key(body.key)
        except InvalidEntitlementKey:
            raise DomainError(422, "INVALID_ENTITLEMENT_KEY", key=body.key) from None
        known = self.registry.feature_keys() if kind == "feature" else self.registry.limit_keys()
        if body.key not in known:
            raise DomainError(422, "UNKNOWN_ENTITLEMENT_KEY", key=body.key)
        _check_override_value(kind, body.value)
        async with self._for_tenant(tenant_id) as conn:
            row = (
                (
                    await conn.execute(
                        _INSERT_OVERRIDE,
                        {
                            "id": uuid4(),
                            "tenant_id": tenant_id,
                            "key": body.key,
                            "value": json.dumps(body.value),
                            "reason": body.reason,
                            "expires_at": body.expires_at,
                            "created_by": _actor(),
                        },
                    )
                )
                .mappings()
                .one()
            )
            created = _override_out(_override(row))
            version = await self._bump(conn, tenant_id)
            await self._emit(
                conn,
                tenant_id,
                version,
                "override_added",
                key=body.key,
                after=created.model_dump(mode="json", by_alias=True),
                reason=body.reason,
            )
        return created

    async def remove_override(self, tenant_id: UUID, override_id: UUID, reason: str) -> None:
        async with self._for_tenant(tenant_id) as conn:
            row = (
                (await conn.execute(_REMOVE_OVERRIDE, {"id": override_id, "tenant_id": tenant_id}))
                .mappings()
                .first()
            )
            if row is None:
                raise NotFoundError(f"override {override_id}")
            removed = _override_out(_override(row))
            version = await self._bump(conn, tenant_id)
            await self._emit(
                conn,
                tenant_id,
                version,
                "override_removed",
                key=removed.key,
                before=removed.model_dump(mode="json", by_alias=True),
                reason=reason,
            )

    async def sweep_expired_overrides(self, tenant_id: UUID) -> int:
        """Soft-delete the expired overrides, one audited event each (ADR 0023 point 5)."""
        async with self._for_tenant(tenant_id) as conn:
            rows = (
                (
                    await conn.execute(
                        _EXPIRE_OVERRIDES, {"tenant_id": tenant_id, "now": self.clock()}
                    )
                )
                .mappings()
                .all()
            )
            if not rows:
                return 0
            version = await self._bump(conn, tenant_id)
            for row in rows:
                expired = _override_out(_override(row))
                await self._emit(
                    conn,
                    tenant_id,
                    version,
                    "override_expired",
                    key=expired.key,
                    before=expired.model_dump(mode="json", by_alias=True),
                    reason="expired",
                )
        return len(rows)

    async def snapshot_usage(
        self,
        tenant_id: UUID,
        period: date,
        *,
        db_bytes: int | None = None,
        measure_db: bool = True,
    ) -> None:
        """Upsert the usage row for ``period``'s month (idempotent; keeps ``over_limit``).

        The database estimate is ``db_bytes`` when given, else measured here when ``measure_db``,
        else the row keeps its last estimate (the nightly run measures only on estimate days).
        """
        async with self._for_tenant(tenant_id) as conn:
            figures = await collect_usage(conn, tenant_id, self._usage_sources)
            if db_bytes is None and measure_db:
                db_bytes = await estimate_db_bytes(conn, tenant_id)
            now = self.clock()
            await conn.execute(
                _UPSERT_USAGE,
                {
                    "id": uuid4(),
                    "tenant_id": tenant_id,
                    "period": month_start(period),
                    "active_users": json.dumps(dict(figures.active_users)),
                    "storage_bytes": figures.storage_bytes or 0,
                    "jobs_count": figures.jobs_count or 0,
                    "ai_spend_cents": figures.ai_spend_cents or 0,
                    "db_bytes_est": db_bytes,
                    "db_estimate_method": None if db_bytes is None else DB_ESTIMATE_METHOD,
                    "db_estimated_at": None if db_bytes is None else now,
                    "captured_at": now,
                },
            )


def _actor() -> UUID | None:
    try:
        return get_context().actor_id
    except ContextMissingError:
        return None


def _gb(value: int | None) -> float | None:
    return None if value is None else math.ceil(value / _GB * 100) / 100


def _used_by_key(usage: RowMapping | None, db_bytes: int | None) -> dict[str, float | None]:
    """The latest snapshot's figures per limit key (seats per class, storage and database GB)."""
    if usage is None:
        return {} if db_bytes is None else {"limit.db_gb": _gb(db_bytes)}
    users: Mapping[str, int] = _jsonb(usage["active_users"]) or {}
    full = sum(users.get(c, 0) for c in ("staff", "field", "full"))
    return {
        "limit.seats.full": float(full),
        "limit.seats.portal": float(users.get("portal", 0)),
        "limit.storage_gb": _gb(usage["storage_bytes"]),
        "limit.db_gb": _gb(db_bytes),
    }
