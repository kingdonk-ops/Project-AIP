"""Workflow presets loaded from ``config/workflows/`` (APPROVALS-08).

A preset is a workflow definition shipped as data by a host module (issues, inspections, ...) so
its lifecycle lives in version control rather than in code. ``ApprovalsApi.install_preset`` reads
one here, validates it and publishes it idempotently.

The directory is ``$AIP_WORKFLOWS_DIR`` when set, else ``<repo root>/config/workflows`` (the same
``repo_root`` override the migrator uses). The file is read only when a preset is installed, never
at import time, so importing the module never touches the filesystem.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["Preset", "PresetError", "load_preset", "workflows_dir"]

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
