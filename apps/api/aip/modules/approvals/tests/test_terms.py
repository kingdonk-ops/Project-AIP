"""APPROVALS-14: every message key the approvals module raises has an en-AU term."""

from __future__ import annotations

import json
import re
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
TERMS = MODULE_DIR.parents[4] / "config" / "terms" / "en-AU" / "approvals.json"

# A ``*_KEY`` constant or a ``messageKey=`` literal naming an ``approvals.`` term.
KEY_RE = re.compile(
    r"(?:_KEY(?::\s*Final)?\s*=\s*|messageKey\s*=\s*)\"(approvals\.[a-z_]+(?:\.[a-z_]+)+)\""
)


def _raised_keys() -> set[str]:
    keys: set[str] = set()
    for path in MODULE_DIR.rglob("*.py"):
        if "tests" in path.relative_to(MODULE_DIR).parts:
            continue
        keys |= set(KEY_RE.findall(path.read_text(encoding="utf-8")))
    return keys


def test_the_scan_finds_the_known_keys() -> None:
    assert {"approvals.comment.required", "approvals.route.pending"} <= _raised_keys()


def test_every_approvals_message_key_resolves_in_en_au() -> None:
    terms = json.loads(TERMS.read_text(encoding="utf-8"))
    missing = sorted(k for k in _raised_keys() if k not in terms)
    assert missing == []
    for key in _raised_keys():
        assert terms[key]["text"].strip()
        assert terms[key]["description"].strip()
