"""The render contract: template + data -> one inert HTML document (REPORTS-01).

``render_html`` turns a template (a stored ``TemplateRow`` or a loaded ``TemplatePackage``) and a
plain data dict into a self-contained, script-free, network-free HTML document. REPORTS-02 hands
``RenderedDocument.html`` and ``assets`` (sibling files) to Gotenberg with ``page`` as the paper
settings; REPORTS-03 builds the inspection data. It is pure: no database, no network, no clock, so
the same template, data, labels, locale and zone give byte-identical HTML.

- The body runs in ``ImmutableSandboxedEnvironment`` (autoescape on, ``StrictUndefined``, no
  loader). The ``safe`` and ``xmlattr`` filters are removed; ``html_policy.check_template`` has
  already refused ``include``/``import``/``extends``, ``|safe``, ``{% autoescape false %}`` and
  ``markup`` at upload.
- Filters (also callable as functions): ``t(key, **args)`` formats a label the caller resolved
  (``labels``) with ICU arguments, and only for keys the definition declares in ``termKeys``;
  ``fmt_datetime``/``fmt_date`` show a UTC instant in ``time_zone`` (ADR 0025); ``fmt_measure``
  shows an SI value in ``unit_system``; ``asset(name)`` gives a declared asset's file name.
  ``time_zone`` and ``locale`` are also template globals.
- The wrapper owns ``<head>``: charset, a Content-Security-Policy meta (a second layer under the
  HTML policy), the ``@page`` rule from the definition, then the template stylesheet.
- The body is streamed and aborted above 5 MB, then checked again with ``check_html`` (a data value
  such as ``javascript:alert(1)`` in an ``href`` fails here).

Every failure is a ``RenderContractError`` with a stable ``code`` (``RENDER_ERROR_CODES``).
"""

from __future__ import annotations

import base64
import html
import re
import zoneinfo
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Final, Literal, Protocol

from babel import Locale, UnknownLocaleError
from babel.dates import format_date, format_time
from jinja2 import StrictUndefined, Template, TemplateError, UndefinedError
from jinja2.exceptions import SecurityError
from jinja2.sandbox import ImmutableSandboxedEnvironment

from aip.modules.report_engine.html_policy import check_html
from aip.modules.terms.api import (
    MessageFormatError,
    UnitSystem,
    UnknownUnitError,
    format_icu,
    to_display,
)

__all__ = [
    "DOCUMENT_CSP",
    "OUTPUT_MAX_BYTES",
    "RENDER_ERROR_CODES",
    "Margins",
    "PageSpec",
    "RenderContractError",
    "RenderableTemplate",
    "RenderedDocument",
    "compile_body",
    "inline_assets",
    "render_html",
]

OUTPUT_MAX_BYTES: Final = 5 * 1024 * 1024
DOCUMENT_CSP: Final = (
    "default-src 'none'; img-src data: file:; font-src data: file:; style-src 'unsafe-inline'"
)
RENDER_ERROR_CODES: Final = (
    "UNKNOWN_TERM_KEY",
    "TERM_FORMAT",
    "UNKNOWN_ASSET",
    "UNKNOWN_UNIT",
    "INVALID_DATETIME",
    "UNKNOWN_TIME_ZONE",
    "UNDEFINED_VALUE",
    "OUTPUT_TOO_LARGE",
    "HTML_POLICY",
    "SANDBOX",
    "RENDER_FAILED",
)
_FALLBACK_LOCALE: Final = "en-AU"
_DATE_STYLES: Final = frozenset({"short", "medium", "long", "full"})


class RenderContractError(Exception):
    """Rendering refused: a stable ``code`` and a short ``detail`` (no data values)."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True, slots=True)
class Margins:
    top: float
    right: float
    bottom: float
    left: float


@dataclass(frozen=True, slots=True)
class PageSpec:
    """Paper settings for the PDF renderer (Gotenberg's paper size, orientation and margins)."""

    paper: Literal["A4", "A3"]
    orientation: Literal["portrait", "landscape"]
    margins_mm: Margins


@dataclass(frozen=True, slots=True)
class RenderedDocument:
    """``html`` refers to each asset by its bare name; ``assets`` are those sibling files."""

    html: str
    assets: dict[str, bytes]
    page: PageSpec
    content_types: dict[str, str]


class RenderableTemplate(Protocol):
    """What ``render_html`` reads: a ``TemplatePackage`` or a stored ``TemplateRow``."""

    @property
    def definition(self) -> Mapping[str, Any]: ...

    @property
    def body(self) -> str: ...

    @property
    def css(self) -> str: ...

    def asset_files(self) -> dict[str, tuple[str, bytes]]: ...


def _sandbox() -> ImmutableSandboxedEnvironment:
    env = ImmutableSandboxedEnvironment(
        autoescape=True, undefined=StrictUndefined, loader=None, auto_reload=False
    )
    for name in ("safe", "xmlattr"):
        env.filters.pop(name, None)
    for name in _FILTER_NAMES:  # placeholders so a body using them compiles; bound per render
        env.filters[name] = _unbound
        env.globals[name] = _unbound
    return env


def _unbound(*_args: Any, **_kwargs: Any) -> str:
    raise RenderContractError("RENDER_FAILED", "filter used outside render_html")


_FILTER_NAMES: Final = ("t", "fmt_datetime", "fmt_date", "fmt_measure", "asset")


def compile_body(body: str) -> Template:
    """The body compiled in the sandbox, as at upload (raises ``TemplateSyntaxError``, e.g. for an
    unknown filter). Each render compiles again with its own bound filters."""
    return _sandbox().from_string(body)


@lru_cache(maxsize=16)
def _babel_locale(locale: str) -> Locale:
    try:
        return Locale.parse(locale, sep="-")
    except (UnknownLocaleError, ValueError):
        return Locale.parse(_FALLBACK_LOCALE, sep="-")


def _instant(value: Any) -> datetime:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            raise RenderContractError("INVALID_DATETIME", "not an RFC 3339 timestamp") from None
    else:
        raise RenderContractError("INVALID_DATETIME", f"cannot format a {type(value).__name__}")
    if moment.tzinfo is None:
        raise RenderContractError("INVALID_DATETIME", "a timestamp needs a UTC offset")
    return moment.astimezone(UTC)


def _margin_css(margins: Margins) -> str:
    return " ".join(
        f"{_num(v)}mm" for v in (margins.top, margins.right, margins.bottom, margins.left)
    )


def _num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def page_spec(definition: Mapping[str, Any]) -> PageSpec:
    m = definition["marginsMm"]
    return PageSpec(
        paper=definition["paper"],
        orientation=definition["orientation"],
        margins_mm=Margins(
            float(m["top"]), float(m["right"]), float(m["bottom"]), float(m["left"])
        ),
    )


@dataclass(frozen=True, slots=True)
class _Filters:
    term_keys: frozenset[str]
    labels: Mapping[str, str]
    locale: str
    zone: zoneinfo.ZoneInfo
    unit_system: UnitSystem
    asset_names: frozenset[str]

    def t(self, key: str, /, **args: Any) -> str:
        if key not in self.term_keys or key not in self.labels:
            raise RenderContractError("UNKNOWN_TERM_KEY", str(key)[:120])
        try:
            return format_icu(self.labels[key], args, self.locale)
        except (MessageFormatError, ArithmeticError, TypeError):
            raise RenderContractError("TERM_FORMAT", str(key)[:120]) from None

    def fmt_datetime(self, value: Any, style: str = "medium") -> str:
        if value is None:
            return ""
        local = _instant(value).astimezone(self.zone)
        lang = _babel_locale(self.locale)
        day = format_date(local, style if style in _DATE_STYLES else "medium", locale=lang)
        clock = format_time(local, "h:mm a", locale=lang)
        return f"{day}, {clock} {local.tzname()}"

    def fmt_date(self, value: Any, style: str = "medium") -> str:
        if value is None:
            return ""
        local = _instant(value).astimezone(self.zone)
        lang = _babel_locale(self.locale)
        return format_date(local, style if style in _DATE_STYLES else "medium", locale=lang)

    def fmt_measure(self, value_si: Any, unit: str) -> str:
        if value_si is None:
            return ""
        try:
            return to_display(float(value_si), unit, self.unit_system).format(self.locale)
        except UnknownUnitError:
            raise RenderContractError("UNKNOWN_UNIT", str(unit)[:40]) from None
        except (TypeError, ValueError):
            raise RenderContractError("RENDER_FAILED", "fmt_measure needs a number") from None

    def asset(self, name: str) -> str:
        if name not in self.asset_names:
            raise RenderContractError("UNKNOWN_ASSET", str(name)[:80])
        return name

    def bound(self) -> dict[str, Callable[..., str]]:
        return {
            "t": self.t,
            "fmt_datetime": self.fmt_datetime,
            "fmt_date": self.fmt_date,
            "fmt_measure": self.fmt_measure,
            "asset": self.asset,
        }


def _zone(time_zone: str) -> zoneinfo.ZoneInfo:
    try:
        return zoneinfo.ZoneInfo(time_zone)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        raise RenderContractError("UNKNOWN_TIME_ZONE", str(time_zone)[:64]) from None


def _render_body(body: str, data: Mapping[str, Any], filters: _Filters) -> str:
    env = _sandbox()
    bound = filters.bound()
    env.filters.update(bound)
    env.globals.update(bound)
    env.globals.update({"locale": filters.locale, "time_zone": filters.zone.key})
    chunks: list[str] = []
    size = 0
    try:
        for chunk in env.from_string(body).generate(dict(data)):
            size += len(chunk.encode("utf-8"))
            if size > OUTPUT_MAX_BYTES:
                raise RenderContractError("OUTPUT_TOO_LARGE", "the body exceeds 5 MB")
            chunks.append(chunk)
    except RenderContractError:
        raise
    except SecurityError:
        raise RenderContractError("SANDBOX", "the template tried an unsafe operation") from None
    except UndefinedError as exc:
        raise RenderContractError("UNDEFINED_VALUE", str(exc)[:120]) from None
    except (TemplateError, TypeError, ValueError, ArithmeticError, LookupError) as exc:
        raise RenderContractError("RENDER_FAILED", type(exc).__name__) from None
    return "".join(chunks)


def render_html(
    template: RenderableTemplate,
    data: Mapping[str, Any],
    *,
    labels: Mapping[str, str],
    locale: str,
    time_zone: str,
    unit_system: UnitSystem,
) -> RenderedDocument:
    """Render ``template`` with ``data`` into a whole, checked HTML document."""
    definition = template.definition
    files = template.asset_files()
    filters = _Filters(
        term_keys=frozenset(definition.get("termKeys", ())),
        labels=dict(labels),
        locale=locale,
        zone=_zone(time_zone),
        unit_system=unit_system,
        asset_names=frozenset(files),
    )
    body = _render_body(template.body, data, filters)
    violations = check_html(body, asset_names=files.keys())
    if violations:
        first = violations[0]
        raise RenderContractError("HTML_POLICY", f"{first.rule} at line {first.line}")

    page = page_spec(definition)
    document = "".join(
        (
            "<!doctype html>\n",
            f'<html lang="{html.escape(locale, quote=True)}">\n<head>\n<meta charset="utf-8">\n',
            f'<meta http-equiv="Content-Security-Policy" content="{DOCUMENT_CSP}">\n',
            f"<style>@page {{ size: {page.paper} {page.orientation}; "
            f"margin: {_margin_css(page.margins_mm)}; }}</style>\n",
            f"<style>\n{template.css}\n</style>\n",
            "</head>\n<body>\n",
            body,
            "\n</body>\n</html>\n",
        )
    )
    return RenderedDocument(
        html=document,
        assets={name: data for name, (_, data) in sorted(files.items())},
        page=page,
        content_types={name: ct for name, (ct, _) in sorted(files.items())},
    )


def inline_assets(document: RenderedDocument) -> str:
    """The document with each asset reference replaced by a ``data:`` URI (the API preview only:
    a browser has no sibling files). Only exact asset names in an attribute or ``url()`` change."""
    out = document.html
    for name, data in document.assets.items():
        encoded = base64.b64encode(data).decode("ascii")
        uri = f"data:{document.content_types[name]};base64,{encoded}"
        quoted = re.escape(name)
        for pattern in (
            rf'(=\s*")({quoted})(")',
            rf"(=\s*')({quoted})(')",
            rf"(url\(\s*[\"']?)({quoted})([\"']?\s*\))",
        ):
            out = re.sub(pattern, rf"\g<1>{uri}\g<3>", out)
    return out
