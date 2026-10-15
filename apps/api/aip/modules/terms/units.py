"""Display units over SI storage (TERMS-03).

Measurement fields store SI (mm, bar, degC). :func:`to_display` converts a stored value into the
unit of a display system and :func:`to_si` converts a typed value back. Conversion never rounds:
``to_si(to_display(x))`` equals ``x`` within :data:`REL_TOL` (or :data:`ABS_TOL` near zero).
Rounding to a unit's decimals happens only in :meth:`Quantity.format`.

The factors are exact by definition: 1 in = 25.4 mm, 1 psi = 0.0689475729 bar,
degF = degC x 9/5 + 32. ``packages/contracts/unit-vectors/units-v1.json`` is the shared contract.

:func:`display_system` reads ``locale_settings.unit_system``: project row, then tenant row, then
``metric``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, get_args
from uuid import UUID

from babel.numbers import format_decimal
from sqlalchemy.ext.asyncio import AsyncConnection

from . import repository
from .icu import babel_locale

__all__ = [
    "ABS_TOL",
    "REL_TOL",
    "UNITS",
    "Quantity",
    "Unit",
    "UnitSystem",
    "UnknownUnitError",
    "display_system",
    "display_unit",
    "round_trips",
    "to_display",
    "to_si",
]

UnitSystem = Literal["metric", "imperial"]
REL_TOL = 1e-9
ABS_TOL = 1e-12


class UnknownUnitError(ValueError):
    """The unit code is not in :data:`UNITS`."""


@dataclass(frozen=True, slots=True)
class Unit:
    """``value_in_unit = value_si * num / den + offset``, kept as a ratio so factors stay exact."""

    code: str
    symbol: str
    si: str
    decimals: int
    num: float = 1.0
    den: float = 1.0
    offset: float = 0.0

    def from_si(self, value: float) -> float:
        return value * self.num / self.den + self.offset

    def into_si(self, value: float) -> float:
        return (value - self.offset) * self.den / self.num


UNITS: dict[str, Unit] = {
    "mm": Unit("mm", "mm", "mm", 2),
    "in": Unit("in", "in", "mm", 2, den=25.4),
    "bar": Unit("bar", "bar", "bar", 2),
    "psi": Unit("psi", "psi", "bar", 2, den=0.0689475729),
    "degC": Unit("degC", "°C", "degC", 1),
    "degF": Unit("degF", "°F", "degC", 1, num=9, den=5, offset=32.0),
}

_DISPLAY: dict[UnitSystem, dict[str, str]] = {
    "metric": {"mm": "mm", "bar": "bar", "degC": "degC"},
    "imperial": {"mm": "in", "bar": "psi", "degC": "degF"},
}


def _unit(code: str) -> Unit:
    try:
        return UNITS[code]
    except KeyError:
        raise UnknownUnitError(f"unknown unit {code!r}") from None


@dataclass(frozen=True, slots=True)
class Quantity:
    """A value in a display unit; ``decimals`` is how many places :meth:`format` shows."""

    value: float
    unit: str
    decimals: int

    def format(self, locale: str = "en-AU") -> str:
        """``1.00 in``: the shortest decimal form of the value (as ICU and Intl read a float),
        rounded half away from zero to ``decimals``, with the locale's symbols."""
        step = Decimal(1).scaleb(-self.decimals)
        rounded = Decimal(repr(self.value)).quantize(step, rounding=ROUND_HALF_UP)
        pattern = "#,##0" + ("." + "0" * self.decimals if self.decimals else "")
        number = format_decimal(rounded, format=pattern, locale=babel_locale(locale))
        return f"{number} {_unit(self.unit).symbol}"


def display_unit(si_unit: str, system: UnitSystem) -> str:
    """The unit ``system`` shows an ``si_unit`` value in."""
    try:
        return _DISPLAY[system][si_unit]
    except KeyError:
        raise UnknownUnitError(f"{si_unit!r} is not an SI storage unit") from None


def to_display(value_si: float, unit: str, system: UnitSystem) -> Quantity:
    """Convert a stored SI value (``unit`` is its SI unit) into ``system``'s display unit."""
    target = _unit(display_unit(unit, system))
    return Quantity(target.from_si(value_si), target.code, target.decimals)


def to_si(value: float, display_unit: str) -> float:
    """Convert a value typed in ``display_unit`` into its SI storage unit."""
    return _unit(display_unit).into_si(value)


def round_trips(original: float, back: float) -> bool:
    """The TERMS-03 tolerance: 1e-9 relative, 1e-12 absolute near zero."""
    return math.isclose(back, original, rel_tol=REL_TOL, abs_tol=ABS_TOL)


async def display_system(
    conn: AsyncConnection, tenant_id: UUID, project_id: UUID | None = None
) -> UnitSystem:
    """The unit system to display in: the project's setting, the tenant's, else ``metric``."""
    found = await repository.unit_system(conn, tenant_id, project_id)
    return found if found in get_args(UnitSystem) else "metric"  # pyright: ignore[reportReturnType]
