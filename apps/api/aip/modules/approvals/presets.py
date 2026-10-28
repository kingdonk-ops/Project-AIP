"""Workflow presets loaded from ``config/workflows/`` (APPROVALS-08).

A preset is a workflow definition shipped as data by a host module (issues, inspections, ...) so
its lifecycle lives in version control rather than in code. ``ApprovalsApi.install_preset`` reads
one here, validates it and publishes it idempotently.

The directory is ``$AIP_WORKFLOWS_DIR`` when set, else ``<repo root>/config/workflows`` (the same
``repo_root`` override the migrator uses). A file is read only when a preset is installed or listed,
never at import time, so importing the module never touches the filesystem.

APPROVALS-05: ``list_presets`` reads and fully validates every preset in the directory (a missing
directory has none); ``create_app`` calls it once so a malformed preset stops startup instead of
failing the first install.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from aip.modules.approvals.schemas import validate_spec

__all__ = ["Preset", "PresetError", "list_presets", "load_preset", "workflows_dir"]

WORKFLOWS_DIR_ENV = "AIP_WORKFLOWS_DIR"
# A preset key is a snake_case file stem; the pattern also keeps the path inside the directory.
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class PresetError(ValueError):
    """A ``config/workflows`` preset is missing, unreadable or malformed."""


@dataclass(frozen=True, slots=True)
class Preset:
    """A workflow definition from ``config/workflows``; ``spec`` is validated by the installer."""

    key: str
    record_type: str
    spec: dict[str, Any]


def workflows_dir() -> Path:
    """The preset directory: ``$AIP_WORKFLOWS_DIR`` or, unset, ``<repo root>/config/workflows``."""
    import os

    override = os.environ.get(WORKFLOWS_DIR_ENV)
    if override:
        return Path(override)
    from aip.platform.db.migrator import repo_root

    return repo_root() / "config" / "workflows"


def load_preset(preset_key: str, base_dir: Path | None = None) -> Preset:
    """Read and shape-check ``<base_dir>/<preset_key>.json``; the spec is validated by the caller.

    Raises :class:`PresetError` for a bad key, a missing or unreadable file, invalid JSON, or a
    file whose ``key`` does not match ``preset_key`` or whose ``recordType`` is not snake_case.
    """
    if not _KEY_RE.fullmatch(preset_key):
        raise PresetError(f"invalid preset key {preset_key!r}: must match {_KEY_RE.pattern}")
    path = (base_dir or workflows_dir()) / f"{preset_key}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PresetError(f"no workflow preset {preset_key!r} (looked in {path.parent})") from None
    except (OSError, json.JSONDecodeError) as exc:
        raise PresetError(f"cannot read workflow preset {preset_key!r}: {exc}") from exc

    if not isinstance(raw, dict):
        raise PresetError(f"preset {preset_key!r} must be a JSON object")
    key = raw.get("key")
    record_type = raw.get("recordType")
    spec = raw.get("spec")
    if key != preset_key:
        raise PresetError(f"preset {preset_key!r} declares key {key!r}; they must match")
    if not isinstance(record_type, str) or not _KEY_RE.fullmatch(record_type):
        raise PresetError(
            f"preset {preset_key!r} needs a snake_case recordType, got {record_type!r}"
        )
    if not isinstance(spec, dict):
        raise PresetError(f"preset {preset_key!r} needs a spec object")
    return Preset(key=preset_key, record_type=record_type, spec=spec)


def list_presets(base_dir: Path | None = None) -> list[Preset]:
    """Every ``*.json`` preset in the directory, sorted by key, each spec checked by ``validate_spec``.

    Raises :class:`PresetError` naming the first preset that is malformed or fails the graph rules.
    """
    directory = base_dir or workflows_dir()
    if not directory.is_dir():
        return []
    presets: list[Preset] = []
    for path in sorted(directory.glob("*.json")):
        preset = load_preset(path.stem, directory)
        try:
            validate_spec(preset.spec)
        except ValidationError as exc:
            raise PresetError(f"preset {preset.key!r} is not a valid workflow: {exc}") from exc
        presets.append(preset)
    return presets
