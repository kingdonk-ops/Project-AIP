"""``PolicyService.can`` (ACCESS-01): grant matching, failure modes and api_client scopes."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

import pytest

from aip.platform.access import (
    AccessPrincipal,
    AssetSubtreeScope,
    Catalogue,
    Forbidden,
    Grant,
    PermissionDef,
    PolicyService,
    ProjectScope,
    Resource,
    TenantScope,
)
from aip.platform.access.policy import _matches  # pyright: ignore[reportPrivateUsage]
from aip.platform.context import RequestContext, use_context

TENANT = UUID("00000000-0000-4000-8000-00000000000a")
OTHER_TENANT = UUID("00000000-0000-4000-8000-00000000000b")
ALICE = UUID("00000000-0000-4000-8000-0000000a11ce")

CODES = ("assets.asset.read", "assets.asset.create", "project.view")
CATALOGUE = Catalogue(PermissionDef(code, code.split(".")[0], code) for code in CODES)
USER = AccessPrincipal(tenant_id=TENANT, actor_id=ALICE)


class FixedGrants:
    def __init__(self, *grants: Grant) -> None:
        self.items = list(grants)
        self.calls = 0

    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        self.calls += 1
        return list(self.items)


class Exploding:
    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        raise RuntimeError("grant store is down")


def policy(*grants: Grant) -> PolicyService:
    return PolicyService(CATALOGUE, [FixedGrants(*grants)])


async def test_tenant_grant_allows_a_resource_in_any_project() -> None:
    decision = await policy(Grant("assets.asset.read", TenantScope())).can(
        USER, "assets.asset.read", Resource(project_id="p1")
    )
    assert decision.allowed
    assert decision.reason == "granted"
    assert decision.matched_grant == Grant("assets.asset.read", TenantScope())


async def test_project_grant_on_p1_denies_a_resource_in_p2() -> None:
    decision = await policy(Grant("assets.asset.read", ProjectScope("p1"))).can(
        USER, "assets.asset.read", Resource(project_id="p2")
    )
    assert not decision.allowed
    assert decision.reason == "no_grant"


async def test_project_grant_allows_the_same_project() -> None:
    project = UUID("00000000-0000-4000-8000-0000000000a1")
    decision = await policy(Grant("assets.asset.read", ProjectScope(project))).can(
        USER, "assets.asset.read", Resource(project_id=str(project))
    )
    assert decision.allowed


@pytest.mark.parametrize("resource", [None, Resource()])
async def test_project_grant_denies_a_resource_without_a_project(
    resource: Resource | None,
) -> None:
    decision = await policy(Grant("assets.asset.read", ProjectScope("p1"))).can(
        USER, "assets.asset.read", resource
    )
    assert not decision.allowed
    assert decision.reason == "no_grant"


async def test_unknown_scope_type_never_matches() -> None:
    odd = Grant("assets.asset.read", object())  # type: ignore[arg-type]
    decision = await policy(odd).can(USER, "assets.asset.read", Resource(project_id="p1"))
    assert not decision.allowed


async def test_raising_provider_gives_provider_error() -> None:
    service = PolicyService(CATALOGUE, [FixedGrants(Grant("assets.asset.read")), Exploding()])
    decision = await service.can(USER, "assets.asset.read")
    assert not decision.allowed
    assert decision.reason == "provider_error"


async def test_unknown_permission_is_denied_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    decision = await policy(Grant("ghost.thing.read")).can(USER, "ghost.thing.read")
    assert not decision.allowed
    assert decision.reason == "unknown_permission"
    assert "ghost.thing.read" in caplog.text


async def test_inactive_principal_is_denied() -> None:
    inactive = AccessPrincipal(tenant_id=TENANT, actor_id=ALICE, active=False)
    decision = await policy(Grant("assets.asset.read")).can(inactive, "assets.asset.read")
    assert decision.reason == "inactive_principal"


async def test_resource_of_another_tenant_is_denied() -> None:
    decision = await policy(Grant("assets.asset.read")).can(
        USER, "assets.asset.read", Resource(tenant_id=OTHER_TENANT)
    )
    assert decision.reason == "no_grant"


async def test_no_provider_denies_everything() -> None:
    service = PolicyService(CATALOGUE)
    assert not (await service.can(USER, "project.view")).allowed


async def test_api_client_is_allowed_exactly_its_scopes() -> None:
    client = AccessPrincipal(
        tenant_id=TENANT, kind="api_client", scopes=frozenset({"assets.asset.read"})
    )
    service = policy(Grant("assets.asset.create"))  # grants do not apply to api clients
    assert (await service.can(client, "assets.asset.read")).allowed
    denied = await service.can(client, "assets.asset.create")
    assert not denied.allowed
    assert denied.reason == "no_grant"


async def test_assert_can_raises_forbidden_with_the_permission() -> None:
    with pytest.raises(Forbidden) as exc:
        await policy().assert_can(USER, "project.view")
    assert exc.value.permission == "project.view"


async def test_filter_allowed_keeps_order() -> None:
    service = policy(
        Grant("project.view", ProjectScope("p1")), Grant("project.view", ProjectScope("p3"))
    )
    items = ["p1", "p2", "p3"]
    kept = await service.filter_allowed(
        USER, "project.view", items, lambda p: Resource(project_id=p)
    )
    assert kept == ["p1", "p3"]


async def test_allowed_permissions_lists_held_codes_sorted() -> None:
    service = policy(Grant("project.view"), Grant("assets.asset.read"))
    assert await service.allowed_permissions(USER) == ["assets.asset.read", "project.view"]


async def test_grants_are_memoised_per_request_only() -> None:
    provider = FixedGrants(Grant("project.view"))
    service = PolicyService(CATALOGUE, [provider])
    with use_context(RequestContext(tenant_id=TENANT, actor_id=ALICE, request_id="r1")):
        await service.can(USER, "project.view")
        await service.can(USER, "assets.asset.read")
    assert provider.calls == 1
    provider.items = []  # e.g. the role changed between requests
    with use_context(RequestContext(tenant_id=TENANT, actor_id=ALICE, request_id="r2")):
        assert not (await service.can(USER, "project.view")).allowed
    assert provider.calls == 2


async def test_without_a_request_context_nothing_is_memoised() -> None:
    provider = FixedGrants(Grant("project.view"))
    service = PolicyService(CATALOGUE, [provider])
    await service.can(USER, "project.view")
    await service.can(USER, "project.view")
    assert provider.calls == 2


async def test_allowed_permissions_fetches_grants_once() -> None:
    provider = FixedGrants(Grant("project.view"), Grant("assets.asset.read", ProjectScope("p1")))
    service = PolicyService(CATALOGUE, [provider])
    assert await service.allowed_permissions(USER) == ["project.view"]
    assert await service.allowed_permissions(USER, Resource(project_id="p1")) == [
        "assets.asset.read",
        "project.view",
    ]
    assert provider.calls == 2  # once per call, not once per catalogue code


async def test_allowed_permissions_fails_closed() -> None:
    assert await PolicyService(CATALOGUE, [Exploding()]).allowed_permissions(USER) == []
    inactive = AccessPrincipal(tenant_id=TENANT, actor_id=ALICE, active=False)
    assert await policy(Grant("project.view")).allowed_permissions(inactive) == []
    other = Resource(tenant_id=OTHER_TENANT)
    assert await policy(Grant("project.view")).allowed_permissions(USER, other) == []


async def test_allowed_permissions_for_an_api_client_are_its_known_scopes() -> None:
    client = AccessPrincipal(
        tenant_id=TENANT, kind="api_client", scopes=frozenset({"project.view", "ghost.thing.read"})
    )
    assert await policy().allowed_permissions(client) == ["project.view"]


# --- PORTAL-01: asset-subtree scope and external principals --------------------------------------

P1 = UUID("00000000-0000-4000-8000-0000000000a1")
P2 = UUID("00000000-0000-4000-8000-0000000000b2")
ROOT = UUID("0192f3c4-0000-7000-8000-000000000001")
NODE = UUID("0192f3c4-0000-7000-8000-000000000002")
CHILD = UUID("0192f3c4-0000-7000-8000-000000000003")
SIBLING = UUID("0192f3c4-0000-7000-8000-000000000004")
SUBTREE = Grant("project.view", AssetSubtreeScope(P1, NODE))


@pytest.mark.parametrize(
    ("resource", "allowed"),
    [
        (Resource(project_id=P1, asset_path=f"{ROOT.hex}.{NODE.hex}.{CHILD.hex}"), True),
        (Resource(project_id=P1, asset_path=f"{ROOT.hex}.{NODE.hex}"), True),
        (Resource(project_id=P1, asset_path=f"{ROOT.hex}.{SIBLING.hex}"), False),
        (Resource(project_id=P1, asset_path=ROOT.hex), False),
        (Resource(project_id=P1, asset_path=None), False),
        (Resource(project_id=P1), False),
        (Resource(project_id=P2, asset_path=f"{ROOT.hex}.{NODE.hex}.{CHILD.hex}"), False),
        (None, False),
    ],
    ids=[
        "child",
        "node",
        "sibling",
        "parent",
        "no-path",
        "no-path-default",
        "other-project",
        "none",
    ],
)
def test_asset_subtree_scope_matches_only_its_subtree_in_its_project(
    resource: Resource | None, allowed: bool
) -> None:
    assert _matches(SUBTREE, "project.view", resource) is allowed


def test_asset_subtree_scope_accepts_string_ids() -> None:
    grant = Grant("project.view", AssetSubtreeScope(str(P1), str(NODE)))
    resource = Resource(project_id=str(P1), asset_path=f"{ROOT.hex}.{NODE.hex}")
    assert _matches(grant, "project.view", resource)


class ExternalGrants(FixedGrants):
    serves_external = True


async def test_an_external_principal_sees_only_external_providers_grants() -> None:
    internal = FixedGrants(Grant("assets.asset.read"))
    external = ExternalGrants(Grant("project.view"))
    service = PolicyService(CATALOGUE, [internal, external])
    portal_user = AccessPrincipal(tenant_id=TENANT, actor_id=ALICE, external=True)

    assert (await service.can(portal_user, "project.view")).allowed
    assert not (await service.can(portal_user, "assets.asset.read")).allowed
    assert await service.allowed_permissions(portal_user) == ["project.view"]
    assert internal.calls == 0


async def test_an_internal_principal_sees_only_internal_providers_grants() -> None:
    internal = FixedGrants(Grant("assets.asset.read"))
    external = ExternalGrants(Grant("project.view"))
    service = PolicyService(CATALOGUE, [internal, external])

    assert (await service.can(USER, "assets.asset.read")).allowed
    assert not (await service.can(USER, "project.view")).allowed
    assert external.calls == 0


async def test_the_request_memo_keeps_internal_and_external_grants_apart() -> None:
    internal = FixedGrants(Grant("assets.asset.read"))
    external = ExternalGrants(Grant("project.view"))
    service = PolicyService(CATALOGUE, [internal, external])
    portal_user = AccessPrincipal(tenant_id=TENANT, actor_id=ALICE, external=True)
    with use_context(RequestContext(tenant_id=TENANT, request_id="r-portal")):
        assert (await service.can(USER, "assets.asset.read")).allowed
        assert not (await service.can(portal_user, "assets.asset.read")).allowed
        assert (await service.can(portal_user, "project.view")).allowed
