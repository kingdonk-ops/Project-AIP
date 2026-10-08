#!/usr/bin/env python3
"""Production strip check (SECURITY-08). Stdlib only, Python 3.12+.

Proves that dev tooling, test code and debug routes are absent from production builds, using the
entries in config/prod-strip-manifest.txt:

- the API image: forbidden and dev-only modules do not import and have no files in the installed
  ``aip`` package, test files are not shipped, source checkouts and tooling paths are absent, and
  the app built with the image's own ``AIP_ENV`` (and with ``AIP_ENV=production``) mounts no debug
  or test-only route;
- the web build (``apps/web/dist`` or the ``aip-web`` image): no source maps, test files or
  dev-only runtime code (React dev runtime, Vite client, HMR hooks).

Usage (from the repo root):
  python3 tools/ci/check_prod_strip.py list                  # the five forbidden entries
  python3 tools/ci/check_prod_strip.py api-image IMAGE       # runs `api-env` inside IMAGE
  python3 tools/ci/check_prod_strip.py web-dist DIR          # a Vite build output directory
  python3 tools/ci/check_prod_strip.py web-image IMAGE       # the dist served by aip-web
  python3 tools/ci/check_prod_strip.py api-env [--image-paths]
      # checks the Python environment running this script; `api-image` pipes this file into
      # the image's interpreter and passes the manifest in $AIP_STRIP_MANIFEST.
Options: --manifest PATH (default config/prod-strip-manifest.txt).
Prints one line per finding and exits 1 if there are any (2 on a usage or manifest error).
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any


def _default_manifest() -> Path:
    # Lazy: inside an image this file runs from stdin or /strip/, with no repo around it.
    return Path(__file__).resolve().parents[2] / "config" / "prod-strip-manifest.txt"


MANIFEST_ENV = "AIP_STRIP_MANIFEST"
WEB_ROOT_IN_IMAGE = "/usr/share/nginx/html"
KINDS = ("forbidden", "dev-module", "dev-glob", "image-path", "route", "web-glob", "web-marker")
MODULE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


class ManifestError(ValueError):
    """The strip manifest is malformed."""


@dataclass(frozen=True)
class Entry:
    kind: str
    value: str
    reason: str = ""


@dataclass(frozen=True)
class StripManifest:
    forbidden: tuple[Entry, ...] = ()
    dev_modules: tuple[str, ...] = ()
    dev_globs: tuple[str, ...] = ()
    image_paths: tuple[str, ...] = ()
    routes: tuple[str, ...] = ()
    web_globs: tuple[str, ...] = ()
    web_markers: tuple[str, ...] = ()
    entries: tuple[Entry, ...] = field(default=(), repr=False)

    @property
    def blocked_modules(self) -> tuple[str, ...]:
        """Every module that must not import: the forbidden five plus dev-only modules."""
        return tuple(e.value for e in self.forbidden) + self.dev_modules


def parse_manifest(text: str) -> StripManifest:
    entries: list[Entry] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        body, _, comment = raw.partition(" #")
        if raw.lstrip().startswith("#"):
            continue
        fields = body.split()
        if not fields:
            continue
        if len(fields) != 2:
            raise ManifestError(f"line {number}: expected '<kind> <value>', got {raw.strip()!r}")
        kind, value = fields
        if kind not in KINDS:
            raise ManifestError(f"line {number}: unknown kind {kind!r} (one of {', '.join(KINDS)})")
        if kind in ("forbidden", "dev-module") and not MODULE_NAME.match(value):
            raise ManifestError(f"line {number}: {value!r} is not a dotted module name")
        if kind in ("image-path", "route") and not value.startswith("/"):
            raise ManifestError(f"line {number}: {kind} {value!r} must start with '/'")
        entries.append(Entry(kind, value, comment.strip()))

    def values(kind: str) -> tuple[str, ...]:
        return tuple(e.value for e in entries if e.kind == kind)

    forbidden = tuple(e for e in entries if e.kind == "forbidden")
    if not forbidden:
        raise ManifestError("no forbidden entries")
    return StripManifest(
        forbidden=forbidden,
        dev_modules=values("dev-module"),
        dev_globs=values("dev-glob"),
        image_paths=values("image-path"),
        routes=values("route"),
        web_globs=values("web-glob"),
        web_markers=values("web-marker"),
        entries=tuple(entries),
    )


def load_manifest(path: Path | None = None) -> StripManifest:
    return parse_manifest((path or _default_manifest()).read_text(encoding="utf-8"))


# --- generic checks ----------------------------------------------------------------------------


def _glob_match(relative: str, pattern: str) -> bool:
    """fnmatch where a leading ``**/`` also matches at the top level."""
    if fnmatch.fnmatchcase(relative, pattern):
        return True
    return pattern.startswith("**/") and fnmatch.fnmatchcase(relative, pattern[3:])


def scan_package_tree(site: Path, manifest: StripManifest) -> list[str]:
    """Findings for the ``aip`` package installed under ``site`` (the dir that holds ``aip/``).

    Any file or directory belonging to a forbidden or dev-only ``aip.*`` module fails, as does any
    path under ``aip/`` that matches a dev glob (tests, conftest).
    """
    errors: list[str] = []
    for module in manifest.blocked_modules:
        if module != "aip" and not module.startswith("aip."):
            continue
        base = site.joinpath(*module.split("."))
        hits = [p for p in (base, base.with_suffix(".py")) if p.exists()]
        hits += [p for p in base.parent.glob(f"{base.name}.*.so")]
        for hit in hits:
            errors.append(f"{module}: present in the package at {hit.relative_to(site).as_posix()}")
    package = site / "aip"
    if package.is_dir():
        for path in sorted(package.rglob("*")):
            relative = path.relative_to(site).as_posix()
            if "__pycache__" in path.parts:
                continue
            for pattern in manifest.dev_globs:
                if _glob_match(relative, pattern):
                    errors.append(f"{relative}: test or dev-only file shipped (matches {pattern})")
                    break
    return errors


def is_importable(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def check_imports(modules: Iterable[str], importable: Callable[[str], bool]) -> list[str]:
    return [
        f"{m}: importable (must raise ImportError in production)" for m in modules if importable(m)
    ]


def _under(path: str, prefix: str) -> bool:
    prefix = prefix.rstrip("/")
    return path == prefix or path.startswith(prefix + "/")


def check_routes(paths: Iterable[str], prefixes: Sequence[str], label: str) -> list[str]:
    return [
        f"route {path}: mounted with {label} (debug/test-only prefix {prefix})"
        for path in sorted(set(paths))
        for prefix in prefixes
        if _under(path, prefix)
    ]


def check_image_paths(paths: Iterable[str], root: Path = Path("/")) -> list[str]:
    return [
        f"{p}: present in the image (source, tooling or tests)"
        for p in paths
        if root.joinpath(p.lstrip("/")).exists()
    ]


def scan_web_dist(dist: Path, manifest: StripManifest) -> list[str]:
    if not (dist / "index.html").is_file():
        return [f"{dist}: no index.html (not a web build output)"]
    errors: list[str] = []
    markers = [m.encode() for m in manifest.web_markers]
    for path in sorted(p for p in dist.rglob("*") if p.is_file()):
        relative = path.relative_to(dist).as_posix()
        matched = [g for g in manifest.web_globs if _glob_match(relative, g)]
        if matched:
            errors.append(f"{relative}: dev-only file in the web build (matches {matched[0]})")
            continue
        data = path.read_bytes()
        for marker, raw in zip(manifest.web_markers, markers, strict=True):
            if raw in data:
                errors.append(f"{relative}: contains dev-only marker {marker!r}")
    return errors


# --- the API environment (runs inside the image) -----------------------------------------------


def _site_of_aip() -> Path | None:
    spec = importlib.util.find_spec("aip")
    if spec is None or not spec.submodule_search_locations:
        return None
    return Path(next(iter(spec.submodule_search_locations))).parent


def route_paths(routes: Iterable[Any], prefix: str = "") -> list[str]:
    """Every path an app or router serves, including routes hidden from the OpenAPI schema.

    Walks Starlette routes and mounts and FastAPI's included-router wrappers (FastAPI >= 0.140
    keeps ``include_router`` lazy, so ``app.routes`` no longer lists the included routes).
    """
    paths: list[str] = []
    for route in routes:
        path = getattr(route, "path", None)
        original = getattr(route, "original_router", None)
        if original is not None:
            context = getattr(route, "include_context", None)
            child_prefix = prefix + str(getattr(context, "prefix", "") or "")
            paths += route_paths(getattr(original, "routes", ()), child_prefix)
        elif isinstance(path, str) and hasattr(route, "routes"):  # Mount
            paths += route_paths(getattr(route, "routes", ()), prefix + path)
        elif isinstance(path, str):
            paths.append(prefix + path)
    return paths


def _app_paths(create_app: Callable[..., Any], env: str) -> list[str]:
    app = create_app(env=env, tracing=False)
    paths = route_paths(app.routes)
    if not any(_under(p, "/api/v1") for p in paths):
        # Fail closed: if a framework change hides the routes, the check must not pass vacuously.
        raise RuntimeError(f"AIP_ENV={env!r}: could not enumerate the app's /api/v1 routes")
    return paths + list(app.openapi().get("paths", {}))


def api_env_errors(manifest: StripManifest, *, image_paths: bool) -> list[str]:
    errors: list[str] = []
    site = _site_of_aip()
    if site is None:
        return ["aip: the API package is not importable in this environment"]
    errors += scan_package_tree(site, manifest)
    errors += check_imports(manifest.blocked_modules, is_importable)
    if image_paths:
        errors += check_image_paths(manifest.image_paths)
    create_app = importlib.import_module("aip.main").create_app
    image_env = os.environ.get("AIP_ENV", "")
    if image_env == "test":
        errors.append("AIP_ENV=test is the image default (mounts test-only routes)")
    for env in dict.fromkeys((image_env, "production")):
        errors += check_routes(_app_paths(create_app, env), manifest.routes, f"AIP_ENV={env!r}")
    return errors


# --- docker wrappers ---------------------------------------------------------------------------


def _docker() -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise SystemExit("check_prod_strip: docker is not on PATH")
    return docker


def api_image_errors(image: str, manifest_text: str) -> tuple[int, str]:
    """Run ``api-env --image-paths`` inside ``image``. Returns (exit code, output)."""
    source = Path(__file__).read_text(encoding="utf-8")
    result = subprocess.run(
        [
            _docker(),
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp",
            "-e",
            MANIFEST_ENV,
            "--entrypoint",
            "python",
            image,
            "-I",
            "-",
            "api-env",
            "--image-paths",
        ],
        input=source,
        capture_output=True,
        text=True,
        env={**os.environ, MANIFEST_ENV: manifest_text},
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def web_image_errors(image: str, manifest: StripManifest) -> list[str]:
    docker = _docker()
    created = subprocess.run([docker, "create", image], capture_output=True, text=True, check=True)
    container = created.stdout.strip()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [docker, "cp", f"{container}:{WEB_ROOT_IN_IMAGE}", tmp],
                capture_output=True,
                check=True,
            )
            return scan_web_dist(Path(tmp) / PurePosixPath(WEB_ROOT_IN_IMAGE).name, manifest)
    finally:
        subprocess.run([docker, "rm", "-f", container], capture_output=True, check=False)


# --- CLI ---------------------------------------------------------------------------------------


def _report(errors: Sequence[str], what: str) -> int:
    for error in errors:
        print(error)
    if errors:
        print(f"check_prod_strip: {len(errors)} finding(s) in {what}")
        return 1
    print(f"check_prod_strip: {what} is clean")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    parser.add_argument("--manifest", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    env_parser = sub.add_parser("api-env")
    env_parser.add_argument("--image-paths", action="store_true")
    for name in ("api-image", "web-image"):
        sub.add_parser(name).add_argument("image")
    sub.add_parser("web-dist").add_argument("dist", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.manifest is None and os.environ.get(MANIFEST_ENV):
            text = os.environ[MANIFEST_ENV]
        else:
            text = (args.manifest or _default_manifest()).read_text(encoding="utf-8")
        manifest = parse_manifest(text)
    except (OSError, ManifestError) as exc:
        print(f"check_prod_strip: manifest: {exc}", file=sys.stderr)
        return 2

    if args.command == "list":
        print("\n".join(e.value for e in manifest.forbidden))
        return 0
    if args.command == "api-env":
        return _report(
            api_env_errors(manifest, image_paths=args.image_paths), "the API environment"
        )
    if args.command == "api-image":
        code, output = api_image_errors(args.image, text)
        print(output, end="")
        return 0 if code == 0 else 1
    if args.command == "web-image":
        return _report(web_image_errors(args.image, manifest), f"web image {args.image}")
    return _report(scan_web_dist(args.dist, manifest), f"web build {args.dist}")


if __name__ == "__main__":
    sys.exit(main())
