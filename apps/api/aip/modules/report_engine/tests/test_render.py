"""REPORTS-01 unit tests: the render contract (no database, no network, no clock)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from aip.modules.report_engine.render import (
    DOCUMENT_CSP,
    RenderContractError,
    RenderedDocument,
    inline_assets,
    render_html,
)
from aip.modules.report_engine.template_package import load_package
from aip.modules.terms.api import to_display
from aip.platform.db.migrator import repo_root

EXAMPLE = repo_root() / "config" / "report-templates" / "project-summary" / "internal" / "v1"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@dataclass
class Tpl:
    """A minimal template for the render contract (a ``RenderableTemplate``)."""

    body: str
    css: str = ""
    term_keys: list[str] = field(default_factory=list[str])
    orientation: str = "portrait"
    paper: str = "A4"
    files: dict[str, tuple[str, bytes]] = field(default_factory=dict[str, tuple[str, bytes]])

    @property
    def definition(self) -> Mapping[str, Any]:
        return {
            "termKeys": self.term_keys,
            "orientation": self.orientation,
            "paper": self.paper,
            "marginsMm": {"top": 10, "right": 12, "bottom": 10, "left": 12.5},
        }

    def asset_files(self) -> dict[str, tuple[str, bytes]]:
        return self.files


def render(
    template: Tpl,
    data: Mapping[str, Any] | None = None,
    *,
    labels: Mapping[str, str] | None = None,
    time_zone: str = "Australia/Perth",
) -> RenderedDocument:
    return render_html(
        template,
        data or {},
        labels=labels or {},
        locale="en-AU",
        time_zone=time_zone,
        unit_system="metric",
    )


def code_of(template: Tpl, data: Mapping[str, Any] | None = None, **kw: Any) -> str:
    with pytest.raises(RenderContractError) as raised:
        render(template, data, **kw)
    return raised.value.code


def test_values_are_autoescaped() -> None:
    doc = render(Tpl("<p>{{ name }}</p>"), {"name": "<b>x</b>"})
    assert "&lt;b&gt;x&lt;/b&gt;" in doc.html and "<b>x</b>" not in doc.html


def test_sandbox_breaches_are_refused() -> None:
    assert code_of(Tpl("{{ ''.__class__.__mro__ }}")) == "SANDBOX"
    assert code_of(Tpl("{{ items.append(1) }}"), {"items": [1]}) == "SANDBOX"


def test_a_rendered_url_is_checked_again() -> None:
    template = Tpl('<a href="{{ link }}">x</a>')
    assert code_of(template, {"link": "javascript:alert(1)"}) == "HTML_POLICY"
    assert '<a href="#section-2">x</a>' in render(template, {"link": "#section-2"}).html


def test_a_data_value_cannot_add_an_element() -> None:
    doc = render(Tpl("<p>{{ v }}</p>"), {"v": "<script>alert(1)</script>"})
    assert "<script>" not in doc.html


def test_t_reads_declared_labels_only() -> None:
    labels = {"report.label.page": "Page", "x.count": "{n, plural, one {# item} other {# items}}"}
    template = Tpl("{{ 'report.label.page' | t }}", term_keys=["report.label.page", "x.count"])
    assert "Page" in render(template, labels=labels).html
    assert (
        "3 items"
        in render(Tpl("{{ t('x.count', n=3) }}", term_keys=["x.count"]), labels=labels).html
    )
    assert code_of(Tpl("{{ 'report.label.page' | t }}"), labels=labels) == "UNKNOWN_TERM_KEY"
    assert code_of(Tpl("{{ 'missing.key' | t }}", term_keys=["missing.key"])) == "UNKNOWN_TERM_KEY"


@pytest.mark.parametrize(
    ("zone", "expected"),
    [
        ("Australia/Perth", "18 Oct 2026, 10:30 am AWST"),
        ("Australia/Sydney", "18 Oct 2026, 1:30 pm AEDT"),
    ],
)
def test_fmt_datetime_shows_the_local_time_with_its_zone(zone: str, expected: str) -> None:
    doc = render(Tpl("{{ fmt_datetime('2026-10-18T02:30:00Z') }}"), time_zone=zone)
    assert expected in doc.html.replace("\u202f", " ")


def test_fmt_date_and_bad_instants() -> None:
    assert (
        "19 Oct 2026"
        in render(Tpl("{{ fmt_date('2026-10-18T22:30:00Z') }}"), time_zone="Australia/Sydney").html
    )
    assert code_of(Tpl("{{ fmt_datetime('2026-10-18T02:30:00') }}")) == "INVALID_DATETIME"
    assert code_of(Tpl("{{ fmt_datetime('yesterday') }}")) == "INVALID_DATETIME"
    assert code_of(Tpl("x"), time_zone="Mars/Olympus") == "UNKNOWN_TIME_ZONE"


def test_fmt_measure_goes_through_to_display() -> None:
    doc = render(Tpl("{{ 12.3 | fmt_measure('mm') }}"))
    assert to_display(12.3, "mm", "metric").format("en-AU") in doc.html
    assert "12.30 mm" in doc.html  # mm shows two decimals (TERMS-03)
    assert code_of(Tpl("{{ 1 | fmt_measure('furlong') }}")) == "UNKNOWN_UNIT"


def test_asset_names_must_be_declared() -> None:
    files = {"logo.png": ("image/png", PNG)}
    doc = render(Tpl("<img src=\"{{ asset('logo.png') }}\">", files=files))
    assert '<img src="logo.png">' in doc.html and doc.assets == {"logo.png": PNG}
    assert code_of(Tpl("{{ asset('other.png') }}", files=files)) == "UNKNOWN_ASSET"


def test_the_wrapper_owns_the_head() -> None:
    doc = render(Tpl("<p>x</p>", css="p { color: red; }", orientation="landscape"))
    assert doc.html.startswith('<!doctype html>\n<html lang="en-AU">')
    assert f'<meta http-equiv="Content-Security-Policy" content="{DOCUMENT_CSP}">' in doc.html
    assert "@page { size: A4 landscape; margin: 10mm 12mm 10mm 12.5mm; }" in doc.html
    assert "p { color: red; }" in doc.html
    assert doc.page.orientation == "landscape" and doc.page.paper == "A4"
    assert doc.page.margins_mm.left == 12.5


def test_a_huge_body_is_aborted() -> None:
    body = "{% for i in range(60000) %}" + "x" * 100 + "{% endfor %}"
    assert code_of(Tpl(body)) == "OUTPUT_TOO_LARGE"


def test_undefined_values_are_errors() -> None:
    assert code_of(Tpl("{{ missing.value }}")) == "UNDEFINED_VALUE"


def test_rendering_is_deterministic() -> None:
    package = load_package(EXAMPLE)
    labels = {key: key.rsplit(".", 1)[-1] for key in package.term_keys}
    labels["report.label.generated_at"] = "Generated {at}"
    first = render_html(
        package,
        package.sample_data,
        labels=labels,
        locale="en-AU",
        time_zone="Australia/Perth",
        unit_system="metric",
    )
    second = render_html(
        package,
        package.sample_data,
        labels=labels,
        locale="en-AU",
        time_zone="Australia/Perth",
        unit_system="metric",
    )
    assert first.html == second.html
    assert "L592" in first.html and 'src="logo.png"' in first.html
    assert "Australia/Perth" in first.html and "AWST" in first.html


def test_inline_assets_replaces_only_asset_references() -> None:
    files = {"logo.png": ("image/png", PNG)}
    doc = render(Tpl("<img src=\"{{ asset('logo.png') }}\"><p>logo.png</p>", files=files))
    inlined = inline_assets(doc)
    assert '<img src="data:image/png;base64,' in inlined and "<p>logo.png</p>" in inlined
