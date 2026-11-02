"""The operator's default role template (ACCESS-09, ADR 0042).

The shipped default levels are ``MATRIX`` in ``default_roles`` (the documented default, mirrored
from ``docs/blueprint/05-access-matrix.md``). An operator may move single cells (module x system
role) to another level; ``default_role_level`` holds only those moved cells, so a cell with no row
is the shipped level and a cell set back to its shipped level loses its row. ``effective_matrix``
is what ``seed_default_roles`` expands, in every tenant and at provisioning.

Every change is written to the append-only ``default_role_level_change`` (who, when, cell, level
before and after, reason) in the same transaction, under one advisory lock so concurrent edits
serialise. ``aip_app`` can only read both tables: its one write path is the SECURITY DEFINER
function ``access_set_default_role_level``, which moves a cell and appends its history row in the
same call, so no change can skip the audit and no history row can be edited.

The template holds levels only, never permission codes, so ADR 0027's expansion still decides
the codes: ``platform.*`` and portal-only codes are never granted (``never_role_held``)
and an unknown verb still needs ``admin``. Guards (error codes in brackets, all 422):

- the role must be one of the 11 system roles [UNKNOWN_ROLE] and the module one the matrix or the
  permission catalogue knows [UNKNOWN_MODULE];
- Client Reviewer stays sign-off only: ``none``, ``view`` or ``approve`` [SIGN_OFF_ONLY_ROLE];
- Tenant Admin keeps ``admin`` on ``access``, so no tenant is left without role management
  [TENANT_ADMIN_LOCKOUT];
- a cell may appear once per request [DUPLICATE_CELL].

The tables are global (no tenant data), so any ``with_tenant`` connection reads them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.access.roles.default_roles import (
    LEVELS,
    MATRIX,
    ROLE_CODES,
    SIGN_OFF_ONLY_ROLES,
    Level,
)
from aip.platform.http import DomainError

__all__ = [
    "LevelChange",
    "TemplateCell",
    "apply_changes",
    "effective_matrix",
    "list_cells",
    "list_history",
    "modules_changed_since",
    "shipped_level",
]

# Levels a sign-off-only role may have: anything above view other than approve adds edit verbs.
SIGN_OFF_ONLY_LEVELS: Final[frozenset[Level]] = frozenset({"none", "view", "approve"})
# The cell that keeps a tenant's role management: never lowered (ADR 0020 "no lockout").
LOCKED_CELL: Final = ("access", "tenant_admin")


@dataclass(frozen=True, slots=True)
class LevelChange:
    module: str
    role: str
    level: Level


@dataclass(frozen=True, slots=True)
class TemplateCell:
    module: str
    role: str
    level: Level
    shipped: Level
    overridden: bool  # a row exists, even one that now equals the shipped level
    updated_by: UUID | None
    updated_at: datetime | None


def shipped_level(module: str, role: str) -> Level:
    """The level ``MATRIX`` ships for the cell; a module the matrix does not list is ``none``."""
    levels = MATRIX.get(module)
    return "none" if levels is None else levels[ROLE_CODES.index(role)]


async def _overrides(conn: AsyncConnection) -> dict[tuple[str, str], dict[str, Any]]:
    rows = await conn.execute(
        text("SELECT module_id, role_code, level, updated_by, updated_at FROM default_role_level")
    )
    return {(r["module_id"], r["role_code"]): dict(r) for r in rows.mappings()}


async def effective_matrix(conn: AsyncConnection) -> dict[str, tuple[Level, ...]]:
    """``MATRIX`` with the operator's moved cells applied (the levels every tenant seeds from)."""
    matrix = {module: list(levels) for module, levels in MATRIX.items()}
    for (module, role), row in (await _overrides(conn)).items():
        levels = matrix.setdefault(module, ["none"] * len(ROLE_CODES))
        levels[ROLE_CODES.index(role)] = cast(Level, row["level"])
    return {module: tuple(levels) for module, levels in matrix.items()}


async def _known_modules(conn: AsyncConnection) -> set[str]:
    rows = await conn.execute(text("SELECT DISTINCT module_id FROM permission"))
    return set(MATRIX) | {r[0] for r in rows}


async def list_cells(conn: AsyncConnection) -> list[TemplateCell]:
    """Every cell of every known module, in module then ``ROLE_CODES`` order."""
    overrides = await _overrides(conn)
    modules = await _known_modules(conn) | {module for module, _ in overrides}
    cells: list[TemplateCell] = []
    for module in sorted(modules):
        for role in ROLE_CODES:
            row = overrides.get((module, role))
            shipped = shipped_level(module, role)
            cells.append(
                TemplateCell(
                    module=module,
                    role=role,
                    level=shipped if row is None else cast(Level, row["level"]),
                    shipped=shipped,
                    overridden=row is not None,
                    updated_by=None if row is None else row["updated_by"],
                    updated_at=None if row is None else row["updated_at"],
                )
            )
    return cells


def _check(change: LevelChange, known: set[str]) -> None:
    if change.role not in ROLE_CODES:
        raise DomainError(422, "UNKNOWN_ROLE", key=change.role)
    if change.module not in known:
        raise DomainError(422, "UNKNOWN_MODULE", key=change.module)
    if change.level not in LEVELS:
        raise DomainError(422, "UNKNOWN_LEVEL", key=change.level)
    if change.role in SIGN_OFF_ONLY_ROLES and change.level not in SIGN_OFF_ONLY_LEVELS:
        raise DomainError(422, "SIGN_OFF_ONLY_ROLE", key=f"{change.module}.{change.role}")
    if (change.module, change.role) == LOCKED_CELL and change.level != "admin":
        raise DomainError(422, "TENANT_ADMIN_LOCKOUT", key=f"{change.module}.{change.role}")


async def apply_changes(
    conn: AsyncConnection,
    changes: Sequence[LevelChange],
    *,
    actor: UUID | None,
    reason: str,
) -> list[dict[str, Any]]:
    """Move cells, all or none; returns the history rows written (a no-op cell writes none).

    Every cell goes through ``access_set_default_role_level``, the only write path ``aip_app`` has
    to the template, which also appends the history row. Setting a cell to its shipped level
    deletes its row, also one the shipped matrix has since caught up with (no history then).
    """
    await conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended('access.default_role_template', 0))")
    )
    known = await _known_modules(conn)
    seen: set[tuple[str, str]] = set()
    for change in changes:
        _check(change, known)
        if (change.module, change.role) in seen:
            raise DomainError(422, "DUPLICATE_CELL", key=f"{change.module}.{change.role}")
        seen.add((change.module, change.role))
    written: list[dict[str, Any]] = []
    for change in changes:
        rows = await conn.execute(
            text("""
            SELECT id, module_id, role_code, level_before, level_after, changed_by, reason,
                   changed_at
            FROM access_set_default_role_level(:module, :role, :level, :shipped, :actor, :reason)
            """),
            {
                "module": change.module,
                "role": change.role,
                "level": change.level,
                "shipped": shipped_level(change.module, change.role),
                "actor": actor,
                "reason": reason,
            },
        )
        written.extend(dict(row) for row in rows.mappings())
    return written


async def list_history(
    conn: AsyncConnection, *, module: str | None = None, role: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    """The newest changes first, optionally for one module and/or role."""
    rows = await conn.execute(
        text("""
        SELECT id, module_id, role_code, level_before, level_after, changed_by, reason, changed_at
        FROM default_role_level_change
        WHERE (CAST(:module AS text) IS NULL OR module_id = :module)
          AND (CAST(:role AS text) IS NULL OR role_code = :role)
        ORDER BY changed_at DESC, id
        LIMIT :limit
        """),
        {"module": module, "role": role, "limit": limit},
    )
    return [dict(r) for r in rows.mappings()]


async def modules_changed_since(
    conn: AsyncConnection, since: datetime
) -> Mapping[str, frozenset[str]]:
    """Per role, the modules whose template level changed after ``since`` (pending reports)."""
    rows = await conn.execute(
        text(
            "SELECT DISTINCT role_code, module_id FROM default_role_level_change"
            " WHERE changed_at > :since"
        ),
        {"since": since},
    )
    out: dict[str, set[str]] = {}
    for role, module in rows:
        out.setdefault(role, set()).add(module)
    return {role: frozenset(modules) for role, modules in out.items()}
