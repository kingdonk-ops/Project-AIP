"""FastAPI application factory.

Run with: ``uvicorn aip.main:create_app --factory``

At boot the module registry (ARCH-02) loads every module manifest and mounts the enabled modules'
routers under ``/api/v1`` in dependency order. ``AIP_MODULES_PACKAGE`` overrides the package that
holds the modules and ``AIP_DISABLED_MODULES`` (comma-separated) skips modules. Any registry
error propagates, so a bad module set stops the process from starting.

Every request passes through the request-context middleware (ARCH-04), which resolves the
principal and project membership; the default resolvers deny everyone. With ``AIP_ENV=test`` and
``AUTH_TEST_STUB=1`` the identity test stub (``x-test-principal``, IDENTITY-02) authenticates
instead; ``AUTH_TEST_STUB`` in any other environment stops startup with a ``RuntimeError``.

Observability (OPS-04): ``RequestIdMiddleware`` is the outermost middleware (request id, JSON
request log line); logs are JSON on stdout with the PII scrubber; OpenTelemetry tracing starts when
``OTEL_EXPORTER_OTLP_ENDPOINT`` is set. ``/api/v1/health/live`` and ``/api/v1/health/ready`` come
from ``aip.modules.ops.health`` and are mounted here, outside the module registry, as is
``/api/v1/platform/version`` (STACK-05, ``aip.platform.version``).

Access (ACCESS-01): the permission catalogue is built from the enabled modules' manifests (an
invalid or duplicate code stops startup), every route must declare ``public()``,
``authenticated()`` or ``requires()`` (``install_access`` refuses to start otherwise), and the
lifespan startup hook syncs the catalogue into the ``permission`` table. When the access module is
enabled, ``RoleGrantProvider`` (ACCESS-02) turns role assignments into grants; without it every
``requires()`` route answers 403.
"""

import os
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel

from aip.modules.access.api import RoleGrantProvider, sync_catalogue
from aip.modules.identity.api import (
    PlatformPrincipalAdapter,
    add_session_middleware,
    get_principal,
    install_session_errors,
    session_resolver,
    stub_principal_resolver,
)
from aip.modules.ops.health import ReadinessChecker
from aip.modules.ops.health import router as health_router
from aip.modules.tenancy.api import (
    DEMO_ENV,
    FlagEntitlements,
    active_tenant_guard,
    assert_demo_has_no_real_customers,
)
from aip.modules.terms.api import install as install_term_resolver
from aip.platform.access import (
    AccessPrincipal,
    PolicyService,
    authenticated,
    build_catalogue,
    check_routes,
    enforce_routes,
    install_access,
    public,
)
from aip.platform.capabilities import validate_capability_settings
from aip.platform.context import (
    ContextMissingError,
    DenyAllMembershipResolver,
    DenyAllPrincipalResolver,
    PrincipalResolver,
    ProjectMembershipResolver,
    RequestContextMiddleware,
    get_context,
)
from aip.platform.db.tls import check_transport_security
from aip.platform.events.dead_letter_routes import (
    create_router as create_dead_letter_router,
)
from aip.platform.events.registry import (
    load_module_events,
    register_platform_events,
    verify_manifest_events,
    verify_released_schemas,
)
from aip.platform.events.routes import create_router as create_events_router
from aip.platform.events.subscribers import verify_manifest_subscribers
from aip.platform.flags import requires_flag
from aip.platform.flags.routes import FLAGS_MANAGE_PERMISSION
from aip.platform.flags.routes import create_router as create_flags_router
from aip.platform.http import install_error_handlers
from aip.platform.modules.registry import load_modules
from aip.platform.modules.routes import create_router as create_modules_router
from aip.platform.observability.logging import RequestIdMiddleware, configure_logging
from aip.platform.observability.otel import init_tracing
from aip.platform.version import router as version_router

# The environments that serve /docs, /redoc and /openapi.json (SECURITY-09, review 11 L4).
DOCS_ENVS = frozenset({"development", "test"})


class HealthResponse(BaseModel):
    """Body of GET /api/v1/health. Changing it changes the generated client (STACK-03)."""

    status: str


def operation_id(route: APIRoute) -> str:
    """Stable OpenAPI operation ids, ``<first tag>_<function name>`` (STACK-03).

    The generated client names its hooks after these (``platform_health`` -> ``usePlatformHealth``).
    """
    return f"{route.tags[0]}_{route.name}" if route.tags else route.name


async def identity_access_principal(request: Request) -> AccessPrincipal:
    """The identity principal (401 when absent or inconsistent) as the policy's principal."""
    principal = await get_principal(request)
    return AccessPrincipal(
        tenant_id=principal.tenant_id, actor_id=principal.user_id, kind="user", aal=principal.aal
    )


def create_app(
    modules_package: str | None = None,
    disabled_modules: Iterable[str] | None = None,
    *,
    principal_resolver: PrincipalResolver | None = None,
    membership_resolver: ProjectMembershipResolver | None = None,
    env: str | None = None,
    readiness: ReadinessChecker | None = None,
    tracing: bool = True,
) -> FastAPI:
    configure_logging()
    validate_capability_settings()  # unknown OBJECT_STORE / PDF_RENDERER stops startup (STACK-02)
    check_transport_security()  # production needs verified TLS to Postgres and Redis (STACK-07)
    modules = load_modules(modules_package, disabled_modules)
    # ARCH-06: load each module's events.py and the platform events, then fail fast if a manifest
    # and its registered models disagree or a released payload schema drifted from its contract.
    load_module_events(modules)
    register_platform_events()
    verify_manifest_events(modules)
    verify_manifest_subscribers(modules)  # ARCH-07: subscribers listed in manifests
    verify_released_schemas()
    catalogue = build_catalogue(module.manifest for module in modules)  # ACCESS-01
    policy = PolicyService(catalogue)
    if any(module.manifest.id == "access" for module in modules):
        policy.register(RoleGrantProvider())  # ACCESS-02: role assignments are the grants
    env = os.environ.get("AIP_ENV", "") if env is None else env

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Routes added after create_app(): refuse to serve them undeclared, and convert them.
        check_routes(app.router.routes, catalogue, app)
        enforce_routes(app)
        if env == DEMO_ENV:  # OPS-11 / ADR 0007: the demo never runs with real customer data
            await assert_demo_has_no_real_customers()
        await sync_catalogue(catalogue)
        yield

    # SECURITY-09 (owner, 2026-10-12): no /docs, /redoc or /openapi.json in production. An
    # allowlist (review 11 L4): only development and test serve them, so demo, staging or an unset
    # AIP_ENV never do. The schema is still built in process (app.openapi()) for codegen and the
    # strip check.
    docs = env in DOCS_ENVS
    app = FastAPI(
        title="AIP API",
        version="0.1.0",
        generate_unique_id_function=operation_id,
        lifespan=lifespan,
        openapi_url="/openapi.json" if docs else None,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
    )

    app.state.readiness = readiness or ReadinessChecker.from_env()

    v1 = APIRouter(prefix="/api/v1")

    @v1.get("/health", tags=["platform"], dependencies=[Depends(public())])
    def health() -> HealthResponse:  # pyright: ignore[reportUnusedFunction]
        return HealthResponse(status="ok")

    # OPS-04 probes, mounted outside the module registry so AIP_DISABLED_MODULES cannot drop them.
    v1.include_router(health_router)
    # STACK-05: build, commit and dependency versions (also outside the registry).
    v1.include_router(version_router)

    if env == "test":
        # ARCH-04: test-only echo of the request context. Never mounted outside AIP_ENV=test.
        @v1.get("/_debug/context", include_in_schema=False, dependencies=[Depends(authenticated())])
        async def debug_context() -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]
            ctx = get_context()
            return {
                "tenant_id": str(ctx.tenant_id),
                "project_id": None if ctx.project_id is None else str(ctx.project_id),
                "actor_id": None if ctx.actor_id is None else str(ctx.actor_id),
                "asset_path_scope": list(ctx.asset_path_scope),
                "request_id": ctx.request_id,
            }

        # ARCH-08: test-only route behind the bim release flag.
        @v1.get(
            "/_fixtures/bim-probe",
            include_in_schema=False,
            dependencies=[Depends(authenticated()), Depends(requires_flag("bim"))],
        )
        async def bim_probe() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
            return {"status": "ok"}

    v1.include_router(create_modules_router(modules))
    # ARCH-06: the event catalogue is gated by platform.events.manage, which the ops module
    # declares. Mount it only when that permission is in the catalogue, so an app built from a
    # module set without ops (test fixtures) does not mount routes whose permission is absent.
    if "platform.events.manage" in catalogue:
        # ARCH-07: before the catalogue, whose /{event_name} would match dead-letter.
        v1.include_router(create_dead_letter_router())
        v1.include_router(create_events_router(modules))  # /admin/platform/events
    # ARCH-08: tenant feature flags. The nav reads them always; changing one needs
    # tenant.flags.manage, mounted only when tenancy (which declares it) is in the module set.
    v1.include_router(create_flags_router(manage=FLAGS_MANAGE_PERMISSION in catalogue))
    for module in modules:
        v1.include_router(module.router)

    app.include_router(v1)
    app.state.modules = modules
    if any(module.id == "tenancy" for module in modules):
        # ENT-01: a requires_flag(x) route also needs the tenant's feature.x (review 11 M7).
        app.state.flag_entitlements = FlagEntitlements(app)
    if any(module.id == "terms" for module in modules):
        install_term_resolver()  # TERMS-02: the aip.platform.terms port for emails and PDFs

    @app.exception_handler(ContextMissingError)
    async def context_missing(  # pyright: ignore[reportUnusedFunction]
        request: Request, exc: ContextMissingError
    ) -> JSONResponse:
        # A request reached code that needs a tenant context but no principal was resolved.
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    install_error_handlers(app)  # DATABASE-04: ConflictError 409, NotFoundError 404

    # IDENTITY-03: the session cookie is the principal. The x-test-principal stub (IDENTITY-02)
    # remains only as a fallback under AIP_ENV=test + AUTH_TEST_STUB=1; it refuses production.
    install_session_errors(app)
    identity_resolver = session_resolver(stub_principal_resolver(env))
    app.state.identity_principal_resolver = identity_resolver
    identity_drives_context = False
    if principal_resolver is None:
        principal_resolver = PlatformPrincipalAdapter(identity_resolver)
        identity_drives_context = True

    # ACCESS-01: after every route is mounted. With the identity resolver in charge, requires()
    # uses identity's principal; an injected resolver (tests) is read from the request context.
    install_access(
        app,
        catalogue=catalogue,
        policy=policy,
        principal_source=identity_access_principal if identity_drives_context else None,
        # TENANCY-01: every authenticated() and requires() route refuses an inactive tenant,
        # whether or not it also depends on require_active_tenant (review 11, H2).
        tenant_guard=active_tenant_guard if any(m.id == "tenancy" for m in modules) else None,
    )

    app.add_middleware(
        RequestContextMiddleware,
        principal_resolver=principal_resolver or DenyAllPrincipalResolver(),
        membership_resolver=membership_resolver or DenyAllMembershipResolver(),
    )
    # Outside the context middleware: resolve the session cookie and check CSRF first. CSRF is
    # always on; an injected resolver (tests) only skips the session cookie resolution.
    add_session_middleware(app, resolve_sessions=identity_drives_context)
    # Added last, so it runs first: the request id exists before the context is resolved.
    app.add_middleware(RequestIdMiddleware)
    if tracing:
        app.state.tracing = init_tracing(app)
    return app
