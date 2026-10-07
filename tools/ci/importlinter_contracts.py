"""Custom import-linter contract type ``module_public_api`` (ARCH-03, ADR 0004).

A business module may import another module only through its published surface: for any import
from ``<modules>.<x>.*`` to ``<modules>.<y>.*`` with x != y, the imported module must be
``<modules>.<y>`` or ``<modules>.<y>.api``. Each violation is reported as ``importer -> imported``.

Configuration (in the ``[tool.importlinter]`` or ``.importlinter`` file)::

    contract_types = ["module_public_api: tools.ci.importlinter_contracts.ModulePublicApiContract"]

    [[tool.importlinter.contracts]]
    id = "no-deep-module-import"
    name = "no-deep-module-import"
    type = "module_public_api"
    modules = "aip.modules"

``lint-imports`` puts the current directory on ``sys.path``, so run it from the repo root.
"""

from __future__ import annotations

from typing import cast

from grimp import ImportGraph
from importlinter.application import output
from importlinter.domain import fields
from importlinter.domain.contract import Contract, ContractCheck
from importlinter.domain.imports import Module


def _owner(module: str, root: str) -> str | None:
    """Return the top-level module package (``<root>.<x>``) that ``module`` belongs to."""
    if not module.startswith(root + "."):
        return None
    head = module[len(root) + 1 :].split(".", 1)[0]
    return f"{root}.{head}"


def find_violations(graph: ImportGraph, root: str) -> list[tuple[str, str, list[int]]]:
    """Return ``(importer, imported, line_numbers)`` for every deep cross-module import."""
    violations: list[tuple[str, str, list[int]]] = []
    for importer in sorted(m for m in graph.modules if _owner(m, root) is not None):
        source = _owner(importer, root)
        for imported in sorted(graph.find_modules_directly_imported_by(importer)):
            target = _owner(imported, root)
            if target is None or target == source:
                continue
            if imported in (target, f"{target}.api"):
                continue
            details = graph.get_import_details(importer=importer, imported=imported)
            lines = sorted({d["line_number"] for d in details})
            violations.append((importer, imported, lines))
    return violations


class ModulePublicApiContract(Contract):
    """Modules import other modules only via the package itself or its ``api``."""

    type_name = "module_public_api"

    modules = fields.ModuleField()

    def check(self, graph: ImportGraph, verbose: bool) -> ContractCheck:
        root = cast(Module, self.modules).name
        if root not in graph.modules:
            raise ValueError(f"Module '{root}' does not exist.")
        output.verbose_print(verbose, f"Checking cross-module imports under {root}...")
        violations = find_violations(graph, root)
        return ContractCheck(
            kept=not violations,
            metadata={
                "violations": [
                    {"importer": i, "imported": m, "line_numbers": n} for i, m, n in violations
                ]
            },
        )

    def render_broken_contract(self, check: ContractCheck) -> None:
        root = cast(Module, self.modules).name
        output.print_error(
            f"Modules under {root} may import another module only as {root}.<y> or {root}.<y>.api:",
            bold=True,
        )
        output.new_line()
        for violation in check.metadata["violations"]:
            lines = ", ".join(f"l.{n}" for n in violation["line_numbers"])
            suffix = f" ({lines})" if lines else ""
            output.print_error(f"{violation['importer']} -> {violation['imported']}{suffix}")
        output.new_line()
