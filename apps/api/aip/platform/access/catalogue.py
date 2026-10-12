"""The permission catalogue, assembled from module manifests (ACCESS-01, ADR 0020 point 5).

Each module declares its permissions as ``[[permissions]]`` tables in ``manifest.toml``
(``{code, description, privileged = false}``). ``build_catalogue`` validates them when
``create_app()`` runs and raises ``CatalogueError`` naming the module and code when:

- a code does not match ``CODE_PATTERN`` (two or three lower-case dot-separated segments, for
  example ``project.view`` or ``audit.activity.view``);
- a code's first segment is not one of the module's ``permission_namespaces`` (default: its id);
- two modules claim the same namespace, or a code is declared twice;
- a code's action is a coarse ``write`` (ADR 0020: permissions are atomic flags such as
  ``create``, ``update``, ``submit``, ``sign``).

``load_manifests`` reads manifests from a modules folder without importing any module, so the
permission code generator (``tools/gen_permissions.py``) needs no database or app.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from aip.platform.modules.manifest import ModuleManifest

__all__ = [
    "CODE_PATTERN",
    "Catalogue",
    "CatalogueError",
    "PermissionDef",
    "build_catalogue",
    "load_manifests",
]

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,2}$")
COARSE_ACTIONS = frozenset({"write"})


class CatalogueError(Exception):
    """The module set declares permissions that must not boot."""


@dataclass(frozen=True, slots=True)
class PermissionDef:
    code: str
    module_id: str
    description: str
    privileged: bool = False


class Catalogue(Mapping[str, PermissionDef]):
    """Every declared permission, keyed and iterated by code in sorted order."""

    def __init__(self, permissions: Iterable[PermissionDef] = ()) -> None:
        self._by_code = {p.code: p for p in sorted(permissions, key=lambda p: p.code)}

    def __getitem__(self, code: str) -> PermissionDef:
        return self._by_code[code]

    def __iter__(self) -> Iterator[str]:
        return iter(self._by_code)

    def __len__(self) -> int:
        return len(self._by_code)

    def sync_payload(self) -> list[dict[str, object]]:
        """The rows ``access_sync_permissions(p_catalogue jsonb)`` upserts, sorted by code."""
        return [
            {
                "code": p.code,
                "module_id": p.module_id,
                "description": p.description,
                "is_privileged": p.privileged,
            }
            for p in self._by_code.values()
        ]


def build_catalogue(manifests: Iterable[ModuleManifest]) -> Catalogue:
    """Validate every module's permissions and return the catalogue (see the module docstring)."""
    manifests = sorted(manifests, key=lambda m: m.id)
    owners: dict[str, str] = {}
    for manifest in manifests:
        for namespace in manifest.namespaces:
            owner = owners.setdefault(namespace, manifest.id)
            if owner != manifest.id:
                raise CatalogueError(
                    f"permission namespace {namespace} is claimed by modules {owner} "
                    f"and {manifest.id}"
                )

    found: dict[str, PermissionDef] = {}
    for manifest in manifests:
        for entry in manifest.permissions:
            code = entry.code
            where = f"module {manifest.id}"
            if not CODE_PATTERN.fullmatch(code):
                raise CatalogueError(
                    f"{where}: invalid permission code {code!r}; expected two or three "
                    "lower-case dot-separated segments, e.g. project.view or audit.activity.view"
                )
            if code.split(".", 1)[0] not in manifest.namespaces:
                raise CatalogueError(
                    f"{where}: permission {code} is outside its namespaces "
                    f"{list(manifest.namespaces)}"
                )
            if code.rsplit(".", 1)[1] in COARSE_ACTIONS:
                raise CatalogueError(
                    f"{where}: permission {code} is coarse; declare atomic actions such as "
                    "create, update or submit (ADR 0020 point 5)"
                )
            if code in found:
                raise CatalogueError(f"{where}: duplicate permission {code}")
            found[code] = PermissionDef(
                code=code,
                module_id=manifest.id,
                description=entry.description,
                privileged=entry.privileged,
            )
    return Catalogue(found.values())


def load_manifests(modules_dir: Path) -> list[ModuleManifest]:
    """Every module manifest under ``modules_dir`` (skipping ``_``/``.`` folders), by id.

    Reads TOML only; nothing is imported. Used by the code generator and the OpenAPI enum.
    """
    manifests: list[ModuleManifest] = []
    for folder in sorted(modules_dir.iterdir()):
        path = folder / "manifest.toml"
        if folder.is_dir() and not folder.name.startswith(("_", ".")) and path.is_file():
            manifests.append(ModuleManifest.from_toml(path))
    return manifests
