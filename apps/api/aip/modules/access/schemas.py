"""Pydantic request/response models for access (ACCESS-01).

``PermissionCode`` is a plain string at runtime, but its OpenAPI schema is the enum of every code
declared by the module manifests in ``aip/modules`` (read from TOML, no imports), so the generated
client types abilities as ``PermissionCode[]``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, WithJsonSchema

from aip.platform.access import build_catalogue, load_manifests

_MODULES_DIR = Path(__file__).resolve().parents[1]
PERMISSION_CODES: tuple[str, ...] = tuple(build_catalogue(load_manifests(_MODULES_DIR)))

PermissionCode = Annotated[
    str,
    WithJsonSchema({"type": "string", "enum": list(PERMISSION_CODES), "title": "PermissionCode"}),
]


class AbilitiesResponse(BaseModel):
    """Body of GET /api/v1/access/me/abilities: what the caller may do (the UI hides the rest)."""

    model_config = ConfigDict(frozen=True)

    permissions: list[PermissionCode]
