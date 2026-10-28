"""REPORTS-01 unit tests: the sanitised-HTML policy (no database)."""

from __future__ import annotations

import pytest
from jinja2 import TemplateSyntaxError

from aip.modules.report_engine.html_policy import check_css, check_html, check_template

LOGO = {"logo.png"}


def _rules(html: str, assets: set[str] = LOGO) -> list[str]:
    return [v.rule for v in check_html(html, asset_names=assets)]


def test_plain_html_with_a_declared_asset_passes() -> None:
    assert check_html('<p>ok</p><img src="logo.png">', asset_names=LOGO) == []


@pytest.mark.parametrize(
    "html", ["<script>x</script>", "<SCRIPT>x</SCRIPT>", "<svg><script>x</script></svg>"]
)
def test_a_script_element_is_one_violation(html: str) -> None:
    assert _rules(html) == ["forbidden_element:script"]


@pytest.mark.parametrize(
    "src",
    [
        "http://169.254.169.254/latest/meta-data/",
        "//evil.test/x.png",
        "file:///etc/passwd",
        "/logo.png",
        "../logo.png",
        "https://x.test/logo.png",
    ],
)
def test_external_urls_and_paths_are_refused(src: str) -> None:
    assert _rules(f'<img src="{src}">') == ["external_url"]


def test_an_undeclared_asset_is_refused() -> None:
    assert _rules('<img src="other.png">') == ["undeclared_asset"]


@pytest.mark.parametrize(
    "href",
    [
        "jav&#x61;script:alert(1)",
        "java\tscript:alert(1)",
        " JAVASCRIPT:alert(1)",
        "jav&amp;#x61;script:x",
    ],
)
def test_encoded_and_split_schemes_are_decoded_first(href: str) -> None:
    assert _rules(f'<a href="{href}">x</a>') == ["external_url"]


def test_a_fragment_link_passes() -> None:
    assert _rules('<a href="#section-2">x</a>') == []


def test_event_handlers_and_srcdoc() -> None:
    assert _rules('<p onclick="x()">x</p>') == ["forbidden_attribute:onclick"]
    assert _rules('<iframe srcdoc="<p>x</p>"></iframe>') == [
        "forbidden_element:iframe",
        "forbidden_attribute:srcdoc",
    ]


@pytest.mark.parametrize("tag", ["meta", "link", "base", "title", "form", "object", "embed"])
def test_head_and_embedding_elements_are_forbidden(tag: str) -> None:
    assert _rules(f"<{tag}>") == [f"forbidden_element:{tag}"]


def test_svg_foreign_object_and_animation_are_forbidden() -> None:
    assert _rules("<svg><foreignObject></foreignObject></svg>") == [
        "forbidden_element:foreignobject"
    ]
    assert _rules('<svg><a><animate attributeName="href" to="x"/></a></svg>') == [
        "forbidden_element:animate"
    ]


def test_srcset_checks_every_candidate() -> None:
    assert _rules('<img srcset="logo.png 1x, https://x.test/a.png 2x">') == ["external_url"]


def test_image_data_uris_only() -> None:
    assert _rules('<img src="data:image/png;base64,iVBORw0KGgo=">') == []
    assert _rules('<img src="data:text/html;base64,PHA+">') == ["external_url"]
    assert _rules('<img src="data:image/svg+xml,<svg/>">') == ["external_url"]


def test_css_rules() -> None:
    def rules(css: str, assets: set[str] = LOGO) -> list[str]:
        return [v.rule for v in check_css(css, asset_names=assets)]

    assert rules("@import url(https://x.test/a.css);") == ["css_import", "external_url"]
    assert rules('div{background:url("https://x.test/a.png")}') == ["external_url"]
    assert rules("@font-face{src:url(inter.woff2)}", {"inter.woff2"}) == []
    assert rules("div{width:expression(alert(1))}") == ["css_expression"]
    assert rules("div{-moz-binding:url(logo.png)}") == ["css_binding"]
    assert rules("div{behavior: url(logo.png)}") == ["css_behavior"]
    assert rules("@IMPORT 'x.css';") == ["css_import"]
    assert rules("@\\69mport 'x.css';") == ["css_import"]
    assert rules("p{color:red}</style><script>") == ["css_breakout"]


def test_style_elements_and_attributes_are_checked_as_css() -> None:
    assert _rules("<style>p{background:url(//evil.test/a)}</style>") == ["external_url"]
    assert _rules('<p style="background:url(other.png)">x</p>') == ["undeclared_asset"]


def test_a_violation_never_echoes_more_than_80_characters() -> None:
    long = "https://x.test/" + "a" * 500
    (violation,) = check_html(f'<img src="{long}">', asset_names=LOGO)
    assert len(violation.detail) <= 81
    assert violation.line == 1 and violation.element == "img" and violation.attribute == "src"


def test_template_rules() -> None:
    def rules(source: str) -> list[str]:
        return [v.rule for v in check_template(source, asset_names=LOGO)]

    assert rules('<img src="{{ asset(\'logo.png\') }}"><a href="{{ link }}">x</a>') == []
    assert rules("{{ name|safe }}") == ["safe_filter"]
    assert rules("{% include 'x' %}") == ["include_not_allowed"]
    assert rules("{% import 'x' as y %}") == ["import_not_allowed"]
    assert rules("{% extends 'x' %}") == ["extends_not_allowed"]
    assert rules("{% autoescape false %}{{ x }}{% endautoescape %}") == ["autoescape_disabled"]
    assert rules("{{ markup(x) }}") == ["markup_not_allowed"]
    assert rules("{% if x %}<script>{% endif %}") == ["forbidden_element:script"]
    assert rules('<a href="https://{{ host }}/x">x</a>') == ["external_url"]


def test_a_template_that_does_not_parse_raises() -> None:
    with pytest.raises(TemplateSyntaxError):
        check_template("{% if %}", asset_names=LOGO)
