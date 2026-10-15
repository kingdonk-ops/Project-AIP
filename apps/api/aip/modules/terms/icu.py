"""ICU MessageFormat for server-side text (TERMS-03).

:func:`render` formats one message: ``pyicumessageformat`` parses it and this module walks the AST,
with Babel supplying CLDR plural rules and number symbols. Supported: simple arguments, ``number``
(default, ``integer``, ``percent``; ties round half away from zero on the shortest decimal
form of a float, as ICU does), ``plural`` (``=N`` exact matches, ``offset``, ``#``),
``selectordinal`` and ``select``. :func:`format_message` resolves a dictionary key through the
TERMS-02 resolver first.

The cases in ``packages/contracts/icu-vectors/icu-v1.json`` are the contract: the i18next-icu
client (TERMS-08) must produce the same strings.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal, localcontext
from functools import lru_cache
from typing import Any
from uuid import UUID

import structlog
from babel import Locale, UnknownLocaleError
from babel.numbers import format_decimal, format_percent
from pyicumessageformat import Parser
from sqlalchemy.ext.asyncio import AsyncConnection

from .service import FALLBACK_LOCALE, missing, resolve

__all__ = ["MessageFormatError", "babel_locale", "format_message", "render"]

logger = structlog.stdlib.get_logger(__name__)

Node = str | dict[str, Any]


class MessageFormatError(ValueError):
    """The message does not parse, or an argument it needs is missing or the wrong type."""


@lru_cache(maxsize=64)
def babel_locale(locale: str) -> Locale:
    """The Babel locale for a BCP 47 tag (``en-AU``); unknown tags fall back to ``en-AU``."""
    try:
        return Locale.parse(locale, sep="-")
    except (UnknownLocaleError, ValueError):
        return Locale.parse(FALLBACK_LOCALE, sep="-")


@lru_cache(maxsize=1024)
def _parse(message: str) -> list[Node]:
    try:
        return Parser().parse(message)
    except SyntaxError as exc:
        raise MessageFormatError(f"cannot parse message: {exc}") from exc


def render(message: str, args: Mapping[str, Any], locale: str) -> str:
    """Format ``message`` with ``args`` for ``locale``."""
    return _Renderer(args, babel_locale(locale)).nodes(_parse(message), None)


class _Renderer:
    def __init__(self, args: Mapping[str, Any], locale: Locale) -> None:
        self.args = args
        self.locale = locale

    def nodes(self, nodes: list[Node], hash_value: float | None) -> str:
        return "".join(self.node(n, hash_value) for n in nodes)

    def node(self, node: Node, hash_value: float | None) -> str:
        if isinstance(node, str):
            return node
        if node.get("hash"):
            if hash_value is None:
                raise MessageFormatError("'#' outside a plural")
            return self.decimal(hash_value)
        kind = node.get("type")
        if kind is None:
            return self.plain(node["name"])
        if kind == "number":
            return self.number(self.numeric(node["name"]), node.get("format"))
        if kind == "select":
            value = self.arg(node["name"])
            options = node["options"]
            chosen = options.get(_js_string(value), options["other"])
            return self.nodes(chosen, hash_value)
        if kind in ("plural", "selectordinal"):
            value = self.numeric(node["name"])
            shifted = value - node.get("offset", 0)
            return self.nodes(self.plural_option(node, value, shifted, kind), shifted)
        raise MessageFormatError(f"unsupported argument type {kind!r}")

    def plural_option(self, node: dict[str, Any], value: float, shifted: float, kind: str) -> Any:
        options: dict[str, Any] = node["options"]
        for selector, chosen in options.items():
            if selector.startswith("=") and float(selector[1:]) == value:
                return chosen
        rule = self.locale.ordinal_form if kind == "selectordinal" else self.locale.plural_form
        return options.get(rule(_plural_operand(shifted)), options["other"])

    def arg(self, name: str) -> Any:
        if name not in self.args:
            raise MessageFormatError(f"missing argument {name!r}")
        return self.args[name]

    def numeric(self, name: str) -> float:
        value = self.arg(name)
        if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
            raise MessageFormatError(f"argument {name!r} must be a number")
        return value  # pyright: ignore[reportReturnType]  # Decimal is accepted throughout

    def plain(self, name: str) -> str:
        return _js_string(self.arg(name))

    def decimal(self, value: float) -> str:
        with localcontext(rounding=ROUND_HALF_UP):
            return format_decimal(_to_decimal(value), locale=self.locale)

    def number(self, value: float, style: str | None) -> str:
        if style is None:
            return self.decimal(value)
        if style == "integer":
            whole = _to_decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP)
            return format_decimal(whole, locale=self.locale)
        if style == "percent":
            with localcontext(rounding=ROUND_HALF_UP):
                return format_percent(_to_decimal(value), locale=self.locale)
        raise MessageFormatError(f"unsupported number style {style!r}")


def _to_decimal(value: float | Decimal) -> Decimal:
    """The shortest round-tripping decimal of a float (what ICU, and so Intl, rounds)."""
    return value if isinstance(value, Decimal) else Decimal(repr(value))


def _js_string(value: Any) -> str:
    """JavaScript's ``String(value)`` for the argument types templates pass."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e21:
        return str(int(value))  # String(3.0) is "3", String(1e16) is "10000000000000000"
    return str(value)


def _plural_operand(value: float) -> int | Decimal:
    """Babel's plural rules read visible fraction digits from a Decimal (1.5 is not 1)."""
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return _to_decimal(value)


async def format_message(
    conn: AsyncConnection,
    key: str,
    args: Mapping[str, Any],
    locale: str,
    *,
    tenant_id: UUID,
    client_id: UUID | None = None,
    project_id: UUID | None = None,
) -> str:
    """Resolve ``key`` (TERMS-02 fallback chain) and format it with ``args``.

    A text that cannot be formatted logs ``terms.format_error`` and gives the visible ``⟦key⟧``,
    so raw ICU syntax never reaches a user.
    """
    message = await resolve(
        conn, key, locale, tenant_id=tenant_id, client_id=client_id, project_id=project_id
    )
    try:
        return render(message, args, locale)
    except (MessageFormatError, ArithmeticError, TypeError) as exc:
        logger.warning(
            "terms.format_error", key=key, locale=locale, tenant_id=str(tenant_id), error=str(exc)
        )
        return missing(key)
