"""The sanitised-HTML policy for report templates and rendered reports (REPORTS-01).

A report is printed by headless Chromium (Gotenberg, REPORTS-02), so its HTML must be inert: no
script, no frame, no form, no network. The same allow-list check runs three times — on the
template source at upload (``check_template``, which first blanks out the Jinja spans), on the
stylesheet (``check_css``) and on the rendered body (``check_html``), so a data value that turns
into ``javascript:`` after rendering is caught as well. A Content-Security-Policy meta in the
wrapper (``render.py``) is the second layer.

Rules:

- forbidden elements (``FORBIDDEN_ELEMENTS``): scripting, frames, embedding, forms, media,
  ``link``/``base``/``meta``/``title`` (the wrapper owns ``<head>``) and the SVG animation elements
  (they can rewrite an ``href``);
- forbidden attributes: every ``on*`` handler, ``srcdoc``, ``formaction``, ``http-equiv``, ``ping``;
- a URL (``URL_ATTRIBUTES``, ``url(...)`` in CSS) may only be a ``#fragment``, a declared asset
  name or a ``data:image/(png|jpeg|webp);base64,`` URI. Entities are decoded and whitespace and
  control characters removed before the scheme check, so ``jav&#x61;script:`` and
  ``java\\tscript:`` are both caught;
- CSS may not use ``@import``, ``expression(``, ``-moz-binding``, ``behavior:``, ``image-set(``
  or ``</style``; comments and CSS escapes are removed first.

The Jinja side of ``check_template`` walks ``Environment.parse``: ``include``/``import``/``extends``
(a template may only use its own body), the ``safe`` filter, ``{% autoescape false %}`` and any
``markup`` name are violations. A parse failure is raised as ``jinja2.TemplateSyntaxError``.

Every violation is ``{rule, element, attribute, line}`` plus a ``detail`` that never holds more than
80 characters of the offending value. Stdlib ``html.parser`` only: no new dependency.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Any, Final

from jinja2 import Environment, nodes

__all__ = [
    "FORBIDDEN_ATTRIBUTES",
    "FORBIDDEN_ELEMENTS",
    "URL_ATTRIBUTES",
    "HtmlViolation",
    "check_css",
    "check_html",
    "check_template",
    "check_url",
]

FORBIDDEN_ELEMENTS: Final = frozenset(
    {
        "script",
        "noscript",
        "iframe",
        "frame",
        "frameset",
        "object",
        "embed",
        "applet",
        "link",
        "base",
        "meta",
        "form",
        "input",
        "button",
        "textarea",
        "select",
        "video",
        "audio",
        "source",
        "track",
        "portal",
        "foreignobject",
        "title",
        "animate",
        "animatemotion",
        "animatetransform",
        "set",
        "discard",
    }
)
FORBIDDEN_ATTRIBUTES: Final = frozenset({"srcdoc", "formaction", "http-equiv", "ping"})
URL_ATTRIBUTES: Final = frozenset(
    {
        "href",
        "src",
        "srcset",
        "xlink:href",
        "poster",
        "background",
        "data",
        "action",
        "cite",
        "longdesc",
        "usemap",
    }
)

_DETAIL_MAX: Final = 80
_STRIP = re.compile(r"[\x00-\x20\x7f]+")
_SCHEME = re.compile(r"^[a-z][a-z0-9+.\-]*:", re.IGNORECASE)
_DATA_IMAGE = re.compile(r"^data:image/(png|jpeg|webp);base64,[a-z0-9+/=]*$", re.IGNORECASE)
_JINJA_SPAN = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.DOTALL)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_HEX_ESCAPE = re.compile(r"\\([0-9a-fA-F]{1,6})[ \t\r\n\f]?")
_CSS_CHAR_ESCAPE = re.compile(r"\\(.)", re.DOTALL)
_CSS_URL = re.compile(r"url\(\s*(?:\"([^\"]*)\"|'([^']*)'|([^)]*?))\s*\)", re.IGNORECASE)
_CSS_RULES: Final = (
    (re.compile(r"@import"), "css_import"),
    (re.compile(r"expression\s*\("), "css_expression"),
    (re.compile(r"-moz-binding"), "css_binding"),
    (re.compile(r"behavior\s*:"), "css_behavior"),
    (re.compile(r"image-set\s*\("), "css_image_set"),
    (re.compile(r"</\s*style"), "css_breakout"),
)


@dataclass(frozen=True, slots=True)
class HtmlViolation:
    """One policy breach: ``rule`` is stable (``forbidden_element:script``, ``external_url``)."""

    rule: str
    element: str | None
    attribute: str | None
    line: int
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clip(value: str) -> str:
    return value if len(value) <= _DETAIL_MAX else value[:_DETAIL_MAX] + "…"


def check_url(value: str, *, asset_names: Iterable[str]) -> str | None:
    """The rule a URL breaks (``external_url`` or ``undeclared_asset``), or ``None`` if allowed.

    ``value`` is the already entity-decoded attribute value (``html.parser`` decodes them); it is
    decoded once more so a double-encoded scheme is caught too.
    """
    url = _STRIP.sub("", html.unescape(value))
    if not url or url.startswith("#"):
        return None
    if url.lower().startswith("data:"):
        return None if _DATA_IMAGE.match(url) else "external_url"
    if _SCHEME.match(url) or url.startswith(("/", "\\", ".")) or "/" in url or "\\" in url:
        return "external_url"
    return None if url in set(asset_names) else "undeclared_asset"


def _srcset_urls(value: str) -> Iterator[str]:
    for candidate in value.split(","):
        parts = candidate.split()
        if parts:
            yield parts[0]


def _decode_css(css: str) -> str:
    def hex_char(match: re.Match[str]) -> str:
        code = int(match.group(1), 16)
        return chr(code) if 0 < code <= 0x10FFFF else "�"

    css = _CSS_COMMENT.sub(" ", css)
    css = _CSS_HEX_ESCAPE.sub(hex_char, css)
    return _CSS_CHAR_ESCAPE.sub(lambda m: m.group(1), css)


def _line_at(text: str, offset: int, first_line: int) -> int:
    return first_line + text.count("\n", 0, offset)


def _css_violations(
    css: str, *, asset_names: frozenset[str], element: str | None, attribute: str | None, line: int
) -> list[HtmlViolation]:
    found: list[HtmlViolation] = []
    # Comments are blanked to the same length so offsets (and line numbers) still line up.
    decoded = _decode_css(_CSS_COMMENT.sub(lambda m: " " * len(m.group(0)), css))
    lowered = decoded.lower()
    for pattern, rule in _CSS_RULES:
        for match in pattern.finditer(lowered):
            found.append(
                HtmlViolation(
                    rule,
                    element,
                    attribute,
                    _line_at(lowered, match.start(), line),
                    _clip(decoded[match.start() : match.start() + _DETAIL_MAX]),
                )
            )
    for match in _CSS_URL.finditer(decoded):
        url = next(group for group in match.groups() if group is not None)
        rule = check_url(url, asset_names=asset_names)
        if rule is not None:
            found.append(
                HtmlViolation(
                    rule, element, attribute, _line_at(decoded, match.start(), line), _clip(url)
                )
            )
    return found


def check_css(css: str, *, asset_names: Iterable[str], first_line: int = 1) -> list[HtmlViolation]:
    """Violations in a stylesheet (``style.css`` or a ``<style>`` element)."""
    return _css_violations(
        css, asset_names=frozenset(asset_names), element=None, attribute=None, line=first_line
    )


class _Checker(HTMLParser):
    def __init__(self, asset_names: frozenset[str]) -> None:
        super().__init__(convert_charrefs=True)
        self.asset_names = asset_names
        self.violations: list[HtmlViolation] = []
        self._style_depth = 0
        self._style_line = 1
        self._style_text: list[str] = []

    def _add(self, rule: str, element: str | None, attribute: str | None, detail: str = "") -> None:
        line = self.getpos()[0]
        self.violations.append(HtmlViolation(rule, element, attribute, line, _clip(detail)))

    def _attributes(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for raw_name, raw_value in attrs:
            name = raw_name.lower()
            value = raw_value or ""
            if name.startswith("on") or name in FORBIDDEN_ATTRIBUTES:
                self._add(f"forbidden_attribute:{name}", tag, name, value)
                continue
            if name == "style":
                self.violations.extend(
                    _css_violations(
                        value,
                        asset_names=self.asset_names,
                        element=tag,
                        attribute=name,
                        line=self.getpos()[0],
                    )
                )
            elif name in URL_ATTRIBUTES:
                urls = _srcset_urls(value) if name == "srcset" else (value,)
                for url in urls:
                    rule = check_url(url, asset_names=self.asset_names)
                    if rule is not None:
                        self._add(rule, tag, name, url)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in FORBIDDEN_ELEMENTS:
            self._add(f"forbidden_element:{tag}", tag, None)
        self._attributes(tag, attrs)
        if tag == "style":
            self._style_depth += 1
            self._style_line = self.getpos()[0]
            self._style_text = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in FORBIDDEN_ELEMENTS:
            self._add(f"forbidden_element:{tag}", tag, None)
        self._attributes(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "style" and self._style_depth:
            self._style_depth -= 1
            self.violations.extend(
                _css_violations(
                    "".join(self._style_text),
                    asset_names=self.asset_names,
                    element="style",
                    attribute=None,
                    line=self._style_line,
                )
            )
            self._style_text = []

    def handle_data(self, data: str) -> None:
        if self._style_depth:
            self._style_text.append(data)

    def close(self) -> None:
        super().close()
        if self._style_depth and self._style_text:  # an unclosed <style> is still checked
            self.handle_endtag("style")


def check_html(source: str, *, asset_names: Iterable[str]) -> list[HtmlViolation]:
    """Every policy violation in an HTML fragment (a template body or a rendered report)."""
    checker = _Checker(frozenset(asset_names))
    checker.feed(source)
    checker.close()
    return checker.violations


def _blank_jinja(source: str) -> str:
    """Each Jinja span replaced by spaces of the same length (newlines kept for line numbers)."""
    return _JINJA_SPAN.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), source)


_LOAD_NODES: Final[tuple[tuple[type[nodes.Node], str], ...]] = (
    (nodes.Include, "include_not_allowed"),
    (nodes.Import, "import_not_allowed"),
    (nodes.FromImport, "import_not_allowed"),
    (nodes.Extends, "extends_not_allowed"),
)


def _jinja_violations(source: str) -> list[HtmlViolation]:
    tree = Environment(autoescape=True).parse(source)
    found: list[HtmlViolation] = []
    for node_type, rule in _LOAD_NODES:
        for node in tree.find_all(node_type):
            found.append(HtmlViolation(rule, None, None, node.lineno))
    for node in tree.find_all(nodes.Filter):
        if node.name == "safe":
            found.append(HtmlViolation("safe_filter", None, None, node.lineno))
        elif node.name.lower() == "markup":
            found.append(HtmlViolation("markup_not_allowed", None, None, node.lineno))
    for node in tree.find_all((nodes.EvalContextModifier, nodes.ScopedEvalContextModifier)):
        for option in node.options:
            if option.key == "autoescape" and not (
                isinstance(option.value, nodes.Const) and option.value.value is True
            ):
                found.append(HtmlViolation("autoescape_disabled", None, None, node.lineno))
    for node in tree.find_all((nodes.Name, nodes.Getattr)):
        name = node.name if isinstance(node, nodes.Name) else node.attr
        if name.lower() == "markup":
            found.append(HtmlViolation("markup_not_allowed", None, None, node.lineno))
    return found


def check_template(source: str, *, asset_names: Iterable[str]) -> list[HtmlViolation]:
    """Violations in a Jinja template body: the Jinja rules, then the HTML policy on the source
    with every ``{{ }}``, ``{% %}`` and ``{# #}`` span blanked out.

    Raises ``jinja2.TemplateSyntaxError`` when the body does not parse.
    """
    found = _jinja_violations(source)
    found.extend(check_html(_blank_jinja(source), asset_names=asset_names))
    return sorted(found, key=lambda v: v.line)
