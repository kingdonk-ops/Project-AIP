"""Jinja filters for email and PDF templates (TERMS-03): no hard-coded labels or units.

Templates render in an async environment (``t`` awaits the resolver) with a
:class:`TemplateScope` that fixes the tenant, project, locale and display unit system::

    env = template_environment(PackageLoader("aip.platform.mail"))
    scope = await template_scope(conn, tenant_id, "en-AU", project_id=project_id)
    html = await render_template(env.get_template("inspection_due.html"), scope, item=item)

In a template, ``{{ 'inspection.status.completed' | t }}`` resolves and formats a key (keyword
arguments become ICU arguments: ``{{ 'defects.count' | t(n=3) }}``), and
``{{ item.thickness_mm | fmt_measure('mm') }}`` shows a stored SI value in the scope's unit system.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from jinja2 import (
    BaseLoader,
    Environment,
    StrictUndefined,
    Template,
    pass_context,
    select_autoescape,
)
from jinja2.runtime import Context
from sqlalchemy.ext.asyncio import AsyncConnection

from .icu import format_message
from .units import UnitSystem, display_system, to_display

__all__ = [
    "SCOPE_VAR",
    "TemplateScope",
    "register_filters",
    "render_template",
    "template_environment",
    "template_scope",
]

SCOPE_VAR = "aip_terms"
"""The template variable :func:`render_template` puts the scope in."""


@dataclass(frozen=True, slots=True)
class TemplateScope:
    """Who a template renders for: the ``with_tenant`` connection and display settings."""

    conn: AsyncConnection
    tenant_id: UUID
    locale: str
    unit_system: UnitSystem
    client_id: UUID | None = None
    project_id: UUID | None = None


async def template_scope(
    conn: AsyncConnection,
    tenant_id: UUID,
    locale: str,
    *,
    client_id: UUID | None = None,
    project_id: UUID | None = None,
) -> TemplateScope:
    """A scope whose unit system comes from ``locale_settings`` (project, tenant, ``metric``)."""
    system = await display_system(conn, tenant_id, project_id)
    return TemplateScope(conn, tenant_id, locale, system, client_id, project_id)


def _scope(ctx: Context) -> TemplateScope:
    scope = ctx.get(SCOPE_VAR)
    if not isinstance(scope, TemplateScope):
        raise RuntimeError("render terms templates with render_template (no TemplateScope set)")
    return scope


@pass_context
async def t(ctx: Context, key: str, /, **args: Any) -> str:
    """Resolve and ICU-format ``key`` for the scope's tenant, client, project and locale."""
    scope = _scope(ctx)
    return await format_message(
        scope.conn,
        key,
        args,
        scope.locale,
        tenant_id=scope.tenant_id,
        client_id=scope.client_id,
        project_id=scope.project_id,
    )


@pass_context
def fmt_measure(ctx: Context, value_si: float | None, unit: str) -> str:
    """Show a stored SI value (``unit`` is its SI unit) in the scope's unit system."""
    if value_si is None:
        return ""
    scope = _scope(ctx)
    return to_display(float(value_si), unit, scope.unit_system).format(scope.locale)


def register_filters(env: Environment) -> None:
    """Add ``t`` and ``fmt_measure`` to an async environment (``enable_async=True``)."""
    if not env.is_async:
        raise ValueError("t awaits the resolver: create the Environment with enable_async=True")
    env.filters["t"] = t
    env.filters["fmt_measure"] = fmt_measure


def template_environment(
    loader: BaseLoader | None = None,
    *,
    autoescape: bool | Callable[[str | None], bool] | None = None,
) -> Environment:
    """An async, strict-undefined environment with the terms filters (HTML autoescaped)."""
    env = Environment(
        loader=loader,
        autoescape=select_autoescape(default_for_string=True) if autoescape is None else autoescape,
        enable_async=True,
        undefined=StrictUndefined,
    )
    register_filters(env)
    return env


async def render_template(template: Template, scope: TemplateScope, /, **context: Any) -> str:
    """Render ``template`` for ``scope``."""
    return await template.render_async(**context, **{SCOPE_VAR: scope})
