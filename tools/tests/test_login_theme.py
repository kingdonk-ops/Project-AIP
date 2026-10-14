"""DESIGN-07: the Keycloak login theme follows the @aip/ui tokens and self-hosts IBM Plex Sans.

Keycloak's pages cannot import packages/ui, so the theme repeats the shared values. These tests fail
when the two drift apart, when the theme loads a font from anywhere but its own resources, or when a
font file it references is missing.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOKENS = ROOT / "packages" / "ui" / "src" / "tokens" / "tokens.css"
THEME = ROOT / "infra" / "keycloak" / "themes" / "aip" / "login"
THEME_CSS = THEME / "resources" / "css" / "aip.css"

# Theme property -> (token block selector, token name). The hover colour is the high-contrast
# accent, the darker accent step the tokens already define.
SHARED = {
    "--aip-color-brand": (":root", "--accent"),
    "--aip-color-brand-hover": ('[data-contrast="high"]', "--accent"),
    "--aip-color-on-brand": (":root", "--accent-foreground"),
    "--aip-color-surface": (":root", "--surface-muted"),
    "--aip-color-text": (":root", "--foreground"),
    "--aip-color-text-muted": (":root", "--foreground-muted"),
    "--aip-color-border": (":root", "--border"),
    "--aip-color-danger": (":root", "--status-danger"),
}

_DECL = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")


def _blocks(css: str) -> dict[str, dict[str, str]]:
    """Custom properties per selector block (no nesting in these files; `@import` lines skipped)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    blocks: dict[str, dict[str, str]] = {}
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        selector = selector.split(";")[-1].strip()
        blocks.setdefault(selector, {}).update(dict(_DECL.findall(body)))
    return blocks


def _resolve(props: dict[str, str], value: str) -> str:
    """Follows `var(--x)` references inside one block until a literal value."""
    seen: set[str] = set()
    while (m := re.fullmatch(r"var\((--[\w-]+)\)", value.strip())) and m.group(1) not in seen:
        seen.add(m.group(1))
        value = props[m.group(1)]
    return value.strip().lower()


def shared_drift(tokens_css: str, theme_css: str) -> list[str]:
    tokens, theme = _blocks(tokens_css), _blocks(theme_css)[":root"]
    drift = []
    for prop, (selector, token) in SHARED.items():
        want = _resolve(tokens[":root"] | tokens[selector], tokens[selector][token])
        got = _resolve(theme, theme.get(prop, "missing"))
        if got != want:
            drift.append(f"{prop} is {got}, but {selector} {token} is {want}")
    return drift


def test_theme_colours_match_the_design_tokens() -> None:
    assert shared_drift(TOKENS.read_text("utf-8"), THEME_CSS.read_text("utf-8")) == []


def test_drift_check_catches_a_token_changed_on_one_side() -> None:
    tokens = TOKENS.read_text("utf-8").replace("--accent: #0f766e;", "--accent: #da291c;", 1)
    assert tokens != TOKENS.read_text("utf-8"), "the default accent moved: update this test"
    assert shared_drift(tokens, THEME_CSS.read_text("utf-8")) == [
        "--aip-color-brand is #0f766e, but :root --accent is #da291c"
    ]


def test_theme_font_is_ibm_plex_sans_like_the_app() -> None:
    tokens = _blocks(TOKENS.read_text("utf-8"))[":root"]
    theme = _blocks(THEME_CSS.read_text("utf-8"))[":root"]
    assert _resolve(theme, theme["--aip-font-family"]) == tokens["--font-sans"].lower()
    assert "inter" not in THEME_CSS.read_text("utf-8").lower()


@pytest.mark.parametrize("weight", ["400", "500", "600"])
def test_fonts_are_self_hosted(weight: str) -> None:
    css = THEME_CSS.read_text("utf-8")
    faces = re.findall(r"@font-face\s*\{([^}]*)\}", css)
    face = next((f for f in faces if re.search(rf"font-weight:\s*{weight}\b", f)), None)
    assert face is not None, f"no @font-face for weight {weight}"
    urls = re.findall(r"url\(\"?([^\")]+)\"?\)", face)
    assert urls, f"weight {weight} has no src"
    assert not any(re.match(r"[a-z]+:|//", u) for u in urls), "fonts load from the theme only"
    for url in urls:
        assert (THEME_CSS.parent / url).resolve().is_file(), f"missing font file {url}"


def test_no_external_requests_and_licence_kept() -> None:
    css = THEME_CSS.read_text("utf-8")
    assert "@import" not in css
    assert not re.search(r"url\(\s*[\"']?(https?:)?//", css)
    assert "SIL Open Font License" in (THEME / "resources" / "fonts" / "OFL.txt").read_text("utf-8")
