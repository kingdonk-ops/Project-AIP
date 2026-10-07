"""Module registry (ARCH-02): discover module manifests, order them by dependency and mount them.

Each business module lives in a sub-package of the modules package (``aip.modules`` by default)
that contains a ``manifest.toml`` and a ``routes.py`` exposing ``router``. At boot the registry

1. discovers every such sub-package (skipping ``_template`` and other ``_``/``.``-prefixed folders),
   validates its manifest and imports it;
2. drops modules listed in ``AIP_DISABLED_MODULES`` (comma-separated), failing if an enabled module
   depends on a disabled one;
3. sorts the rest topologically on ``depends_on`` (alphabetical tie-break, so the order is stable)
   and fails fast on unknown dependencies or cycles.

Any :class:`RegistryError` aborts startup.
"""

from __future__ import annotations

import heapq
import importlib
import os
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from fastapi import APIRouter
from pydantic import ValidationError

from aip.platform.modules.manifest import ModuleManifest

DEFAULT_MODULES_PACKAGE = "aip.modules"
MODULES_PACKAGE_ENV = "AIP_MODULES_PACKAGE"
DISABLED_MODULES_ENV = "AIP_DISABLED_MODULES"


class RegistryError(Exception):
    """A module set that must not boot."""


class ManifestError(RegistryError):
    """A module folder whose manifest or routes are missing or invalid."""


class MissingDependencyError(RegistryError):
    """A module depends on a module that is unknown or disabled."""


class CycleError(RegistryError):
    """Modules depend on each other in a cycle."""


@dataclass(frozen=True)
class LoadedModule:
    """A discovered, validated and imported module."""

    manifest: ModuleManifest
    package: ModuleType
    router: APIRouter

    @property
    def id(self) -> str:
        return self.manifest.id


def _is_candidate(path: Path) -> bool:
    return (
        path.is_dir()
        and not path.name.startswith(("_", "."))
        and (path / "manifest.toml").is_file()
    )


def _load_one(package: str, folder: Path) -> LoadedModule:
    manifest_path = folder / "manifest.toml"
    try:
        manifest = ModuleManifest.from_toml(manifest_path)
    except (ValidationError, tomllib.TOMLDecodeError) as exc:
        raise ManifestError(f"module {folder.name}: invalid {manifest_path}: {exc}") from exc
    if manifest.id != folder.name:
        raise ManifestError(
            f"module {folder.name}: manifest id {manifest.id!r} must match its folder name"
        )

    module_package = importlib.import_module(f"{package}.{folder.name}")
    try:
        routes = importlib.import_module(f"{package}.{folder.name}.routes")
    except ModuleNotFoundError as exc:
        if exc.name != f"{package}.{folder.name}.routes":
            raise
        raise ManifestError(f"module {folder.name}: routes.py is missing") from exc
    router: object = getattr(routes, "router", None)
    if not isinstance(router, APIRouter):
        raise ManifestError(f"module {folder.name}: routes.router must be a fastapi.APIRouter")
    return LoadedModule(manifest=manifest, package=module_package, router=router)


def discover(package: str = DEFAULT_MODULES_PACKAGE) -> list[LoadedModule]:
    """Find, validate and import every module under ``package``, sorted by id."""
    root = importlib.import_module(package)
    search_paths: Iterable[str] | None = getattr(root, "__path__", None)
    if search_paths is None:
        raise RegistryError(f"{package} is not a package")

    found: dict[str, LoadedModule] = {}
    for base in search_paths:
        for folder in sorted(Path(base).iterdir()):
            if not _is_candidate(folder):
                continue
            if folder.name in found:
                raise ManifestError(f"module {folder.name} is defined more than once")
            found[folder.name] = _load_one(package, folder)
    return [found[module_id] for module_id in sorted(found)]


def _find_cycle(remaining: set[str], graph: Mapping[str, list[str]]) -> list[str]:
    """Walk from the smallest unsorted module; every unsorted module has an unsorted dependency."""
    path: list[str] = []
    seen: dict[str, int] = {}
    node = min(remaining)
    while node not in seen:
        seen[node] = len(path)
        path.append(node)
        node = next(dep for dep in graph[node] if dep in remaining)
    return [*path[seen[node] :], node]


def sort_modules(graph: Mapping[str, Iterable[str]]) -> list[str]:
    """Order module ids so each comes after its dependencies; ties break alphabetically.

    Raises :class:`MissingDependencyError` for a dependency not in ``graph`` and
    :class:`CycleError` (naming every module in the cycle) for circular dependencies.
    """
    deps = {module_id: sorted(set(d)) for module_id, d in graph.items()}
    for module_id in sorted(deps):
        for dep in deps[module_id]:
            if dep not in deps:
                raise MissingDependencyError(f"module {module_id} depends on unknown module {dep}")

    pending = {module_id: len(d) for module_id, d in deps.items()}
    dependents: dict[str, list[str]] = {module_id: [] for module_id in deps}
    for module_id, module_deps in deps.items():
        for dep in module_deps:
            dependents[dep].append(module_id)

    ready = [module_id for module_id, count in pending.items() if count == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        module_id = heapq.heappop(ready)
        order.append(module_id)
        for dependent in dependents[module_id]:
            pending[dependent] -= 1
            if pending[dependent] == 0:
                heapq.heappush(ready, dependent)

    if len(order) != len(deps):
        cycle = _find_cycle(set(deps) - set(order), deps)
        raise CycleError(f"module dependency cycle: {' -> '.join(cycle)}")
    return order


def parse_disabled(value: str | None) -> frozenset[str]:
    """Parse ``AIP_DISABLED_MODULES`` (comma-separated module ids)."""
    if not value:
        return frozenset()
    return frozenset(part.strip() for part in value.split(",") if part.strip())


def resolve(modules: Iterable[LoadedModule], disabled: Iterable[str] = ()) -> list[LoadedModule]:
    """Drop disabled modules and return the rest in mount (dependency) order."""
    disabled_ids = frozenset(disabled)
    known = {module.id: module for module in modules}
    enabled = {mid: module for mid, module in known.items() if mid not in disabled_ids}
    for module_id in sorted(enabled):
        for dep in sorted(enabled[module_id].manifest.depends_on):
            if dep in disabled_ids and dep in known:
                raise MissingDependencyError(
                    f"module {module_id} depends on module {dep}, "
                    f"which is disabled by {DISABLED_MODULES_ENV}"
                )
    order = sort_modules({mid: module.manifest.depends_on for mid, module in enabled.items()})
    return [enabled[module_id] for module_id in order]


def load_modules(
    package: str | None = None, disabled: Iterable[str] | None = None
) -> list[LoadedModule]:
    """Discover and resolve modules. ``None`` arguments fall back to the environment."""
    package = package or os.environ.get(MODULES_PACKAGE_ENV) or DEFAULT_MODULES_PACKAGE
    if disabled is None:
        disabled = parse_disabled(os.environ.get(DISABLED_MODULES_ENV))
    return resolve(discover(package), disabled)
