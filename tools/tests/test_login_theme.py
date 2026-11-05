"""DESIGN-07: the Keycloak login theme follows the @aip/ui tokens and self-hosts IBM Plex Sans.

Keycloak's pages cannot import packages/ui, so the theme repeats the shared values. These tests fail
when the two drift apart, when the theme loads a font from anywhere but its own resources, or when a
font file it references is missing. DESIGN-19 adds the DESIGN-09 tokens (canvas, panel hairline,
status tints) and the high-contrast values, which the theme applies under `prefers-contrast: more`.
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
HIGH = '[data-contrast="high"]'
SHARED = {
    "--aip-color-brand": (":root", "--accent"),
    "--aip-color-brand-hover": (HIGH, "--accent"),
    "--aip-color-on-brand": (":root", "--accent-foreground"),
    "--aip-color-canvas": (":root", "--canvas"),
    "--aip-color-panel": (":root", "--surface"),
    "--aip-color-text": (":root", "--foreground"),
    "--aip-color-text-muted": (":root", "--foreground-muted"),
    "--aip-color-border": (":root", "--border"),
    "--aip-color-border-subtle": (":root", "--border-subtle"),
    "--aip-color-border-strong": (":root", "--border-strong"),
    "--aip-color-danger": (":root", "--status-danger"),
    "--aip-color-danger-subtle": (":root", "--status-danger-subtle"),
    "--aip-color-warning": (":root", "--status-warning"),
    "--aip-color-warning-subtle": (":root", "--status-warning-subtle"),
    "--aip-color-success": (":root", "--status-success"),
    "--aip-color-success-subtle": (":root", "--status-success-subtle"),
    "--aip-color-info": (":root", "--status-info"),
    "--aip-color-info-subtle": (":root", "--status-info-subtle"),
    "--aip-radius-lg": (":root", "--radius-lg"),
    "--aip-radius-md": (":root", "--radius-md"),
}

# DESIGN-19: the theme's `@media (prefers-contrast: more) { :root { ... } }` -> the app's
# [data-contrast="high"] tokens (Keycloak's pages cannot read the app's contrast setting).
SHARED_HIGH_CONTRAST = {
    "--aip-color-brand": (HIGH, "--accent"),
    "--aip-color-canvas": (HIGH, "--canvas"),
    "--aip-color-text": (HIGH, "--foreground"),
    "--aip-color-text-muted": (HIGH, "--foreground-muted"),
    "--aip-color-border": (HIGH, "--border"),
    "--aip-color-border-strong": (HIGH, "--border-strong"),
    "--aip-color-border-subtle": (HIGH, "--border-subtle"),
    "--aip-color-danger": (HIGH, "--status-danger"),
    "--aip-color-warning": (HIGH, "--status-warning"),
    "--aip-color-success": (HIGH, "--status-success"),
    "--aip-color-info": (HIGH, "--status-info"),
}

_DECL = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_MEDIA_MORE = re.compile(
    r"@media\s*\(prefers-contrast:\s*more\)\s*\{((?:[^{}]*\{[^{}]*\})*[^{}]*)\}"
)


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _blocks(css: str) -> dict[str, dict[str, str]]:
    """Custom properties per top-level selector block (skips `@media` blocks, `@import` lines)."""
    css = _MEDIA_MORE.sub("", _strip_comments(css))
    blocks: dict[str, dict[str, str]] = {}
    for selector, body in _RULE.findall(css):
        selector = selector.split(";")[-1].strip()
        blocks.setdefault(selector, {}).update(dict(_DECL.findall(body)))
    return blocks


def _high_contrast_root(theme_css: str) -> dict[str, str]:
    """The `:root` overrides inside the theme's `prefers-contrast: more` media blocks."""
    props: dict[str, str] = {}
    for body in _MEDIA_MORE.findall(_strip_comments(theme_css)):
        for selector, block in _RULE.findall(body):
            if selector.strip() == ":root":
                props.update(dict(_DECL.findall(block)))
    return props


def _resolve(props: dict[str, str], value: str) -> str:
    """Follows `var(--x)` references inside one block until a literal value."""
    seen: set[str] = set()
    while (m := re.fullmatch(r"var\((--[\w-]+)\)", value.strip())) and m.group(1) not in seen:
        seen.add(m.group(1))
        value = props[m.group(1)]
    return value.strip().lower()


def _drift(
    tokens: dict[str, dict[str, str]],
    theme: dict[str, str],
    shared: dict[str, tuple[str, str]],
    where: str,
) -> list[str]:
    drift = []
    for prop, (selector, token) in shared.items():
        merged = tokens[":root"] | tokens[selector]
        want = _resolve(merged, merged[token])  # a token the block does not override inherits :root
        got = _resolve(theme, theme.get(prop, "missing"))
        if got != want:
            drift.append(f"{where}{prop} is {got}, but {selector} {token} is {want}")
    return drift


def shared_drift(tokens_css: str, theme_css: str) -> list[str]:
    tokens, theme = _blocks(tokens_css), _blocks(theme_css)[":root"]
    high = theme | _high_contrast_root(theme_css)
    more = "prefers-contrast: more "
    return _drift(tokens, theme, SHARED, "") + _drift(tokens, high, SHARED_HIGH_CONTRAST, more)


def test_theme_colours_match_the_design_tokens() -> None:
    assert shared_drift(TOKENS.read_text("utf-8"), THEME_CSS.read_text("utf-8")) == []


def test_drift_check_covers_the_design_09_tokens() -> None:
    original = TOKENS.read_text("utf-8")
    tokens = original.replace(
        "--status-danger-subtle: #fef2f2;", "--status-danger-subtle: #fee2e2;", 1
    )
    tokens = tokens.replace("--canvas: var(--neutral-50);", "--canvas: var(--neutral-100);", 1)
    moved = tokens.count("#fee2e2") == 1 and "--canvas: var(--neutral-100);" in tokens
    assert moved, "tokens moved: update this test"
    assert shared_drift(tokens, THEME_CSS.read_text("utf-8")) == [
        "--aip-color-canvas is #fafafa, but :root --canvas is #f5f5f5",
        "--aip-color-danger-subtle is #fef2f2, but :root --status-danger-subtle is #fee2e2",
    ]


def test_drift_check_covers_the_high_contrast_values() -> None:
    theme = THEME_CSS.read_text("utf-8")
    assert _high_contrast_root(theme), "the theme has a prefers-contrast: more :root block"
    changed = theme.replace(
        "--aip-color-canvas: #ffffff; /* high-contrast --canvas */", "--aip-color-canvas: #fafafa;", 1
    )
    assert changed != theme, "the high-contrast canvas moved: update this test"
    assert shared_drift(TOKENS.read_text("utf-8"), changed) == [
        "prefers-contrast: more --aip-color-canvas is #fafafa, "
        'but [data-contrast="high"] --canvas is #ffffff'
    ]


def test_accent_is_never_a_surface_fill_in_the_theme() -> None:
    """DESIGN-09 step 5: the accent fills only the primary button, never a panel or alert."""
    css = _MEDIA_MORE.sub("", _strip_comments(THEME_CSS.read_text("utf-8")))
    fills = [
        selector.strip()
        for selector, body in _RULE.findall(css)
        if re.search(r"background(-color)?\s*:\s*var\(--aip-color-brand", body)
    ]
    assert fills and all(".pf-m-primary" in f for f in fills), fills


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
