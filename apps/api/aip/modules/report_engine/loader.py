"""Install the config report templates for tenants (REPORTS-01).

    DATABASE_URL=... python -m aip.modules.report_engine.loader config/report-templates \\
        --tenant <uuid> [--tenant <uuid> ...]

Like ``aip-access seed-roles`` it runs as ``aip_app`` (RLS on) with one ``with_tenant``
transaction per tenant, because no application role can list every tenant. Every package under
``<root>/<key>/<variant>/v<version>/`` is loaded and validated first (a bad package, or a folder
whose name disagrees with its ``template.json``, stops the run before anything is written). Then,
per tenant and package:

- no ``(key, variant, version)`` row: insert it as ``published`` with ``source = 'config'`` and
  emit ``report.template_published``;
- a row with the same ``content_sha256``: skip it;
- a row with a different hash: print ``TEMPLATE_VERSION_CHANGED key=<key> variant=<variant>
  version=<n>`` and exit 1, writing nothing for that tenant (a changed template needs a new
  version folder).

It prints ``<tenant>: installed N, unchanged M`` per tenant. Idempotent.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO
from uuid import UUID

from aip.modules.report_engine import repository as repo
from aip.modules.report_engine.service import TemplateService
from aip.modules.report_engine.template_package import (
    TemplatePackage,
    TemplatePackageError,
    load_package,
)
from aip.platform.context import RequestContext, new_request_id, use_context
from aip.platform.db.engine import dispose_engine
from aip.platform.db.session import with_tenant

__all__ = ["LoadReport", "TemplateVersionChangedError", "discover", "load", "main"]

_VERSION_DIR = re.compile(r"^v([1-9][0-9]*)$")


class TemplateVersionChangedError(Exception):
    """A stored version differs from its package: it needs a new version folder."""

    def __init__(self, package: TemplatePackage) -> None:
        self.package = package
        super().__init__(
            f"TEMPLATE_VERSION_CHANGED key={package.key} variant={package.variant} "
            f"version={package.version}"
        )


@dataclass(frozen=True, slots=True)
class LoadReport:
    tenant_id: UUID
    installed: int
    unchanged: int


def discover(root: Path) -> list[TemplatePackage]:
    """Every package under ``root``, validated, in key/variant/version order."""
    packages: list[TemplatePackage] = []
    for folder in sorted(root.glob("*/*/v*")):
        match = _VERSION_DIR.match(folder.name)
        if not folder.is_dir() or match is None:
            continue
        try:
            package = load_package(folder)
        except TemplatePackageError as exc:
            raise TemplatePackageError(
                exc.code, exc.path, f"{folder.relative_to(root)}: {exc.detail}", exc.violations
            ) from None
        expected = (folder.parent.parent.name, folder.parent.name, int(match.group(1)))
        if (package.key, package.variant, package.version) != expected:
            raise TemplatePackageError(
                "SCHEMA_INVALID",
                "",
                f"{folder.relative_to(root)}: template.json says {package.key}/"
                f"{package.variant}/v{package.version}",
            )
        packages.append(package)
    return packages


async def load(packages: Sequence[TemplatePackage], tenant_id: UUID) -> LoadReport:
    """Install ``packages`` for one tenant in one transaction (all or nothing)."""
    service = TemplateService()
    installed = unchanged = 0
    ctx = RequestContext(tenant_id=tenant_id, request_id=new_request_id())
    with use_context(ctx):
        async with with_tenant(ctx) as conn:
            for package in packages:
                row = await repo.find_version(conn, package.key, package.variant, package.version)
                if row is None:
                    await service.install_published(conn, package)
                    installed += 1
                elif row["content_sha256"] == package.content_sha256:
                    unchanged += 1
                else:
                    raise TemplateVersionChangedError(package)
    return LoadReport(tenant_id, installed, unchanged)


async def run(
    root: Path, tenants: Sequence[UUID], *, out: TextIO = sys.stdout, err: TextIO = sys.stderr
) -> int:
    """Load every package for every tenant; the exit code (0, or 1 on any failure)."""
    try:
        packages = discover(root)
    except TemplatePackageError as exc:
        print(f"{exc.code} {exc.path}: {exc.detail}", file=err)
        return 1
    status = 0
    for tenant in tenants:
        try:
            report = await load(packages, tenant)
        except TemplateVersionChangedError as exc:
            print(f"{tenant}: {exc}", file=err)
            status = 1
            continue
        print(f"{tenant}: installed {report.installed}, unchanged {report.unchanged}", file=out)
    return status


async def _main(root: Path, tenants: Sequence[UUID]) -> int:
    try:
        return await run(root, tenants)
    finally:
        await dispose_engine()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m aip.modules.report_engine.loader")
    parser.add_argument("root", type=Path, help="the config/report-templates folder")
    parser.add_argument("--tenant", type=UUID, action="append", required=True, help="tenant id")
    args = parser.parse_args(argv)
    if not args.root.is_dir():
        print(f"{args.root} is not a folder", file=sys.stderr)
        return 2
    return asyncio.run(_main(args.root, args.tenant))


if __name__ == "__main__":
    raise SystemExit(main())
