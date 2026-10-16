"""TESTING-04: the permission matrix, generated from the catalogue and the default-role seed.

One case per (role, permission, assignment state, assignment scope, resource scope):

- ``assigned``: whether the principal holds the role at all (False proves deny by default);
- ``assignment``: ``tenant`` (the whole tenant) or ``project`` (project P1 only);
- ``in_scope``: whether the resource is in P1 (True) or in another project, P2 (False).

A case expects allow only when the role is assigned, the role grants the permission, and the
scope matches: a tenant assignment matches every project, a project assignment only P1.
Adding a permission to a manifest (or a level to the matrix) adds its cases automatically.

Asset-subtree scope is not generated yet: the policy has no asset scope until ACCESS-03.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

__all__ = ["ASSIGNMENTS", "Assignment", "MatrixCase", "matrix_cases"]

Assignment = Literal["tenant", "project"]
ASSIGNMENTS: tuple[Assignment, ...] = ("tenant", "project")


@dataclass(frozen=True, slots=True)
class MatrixCase:
    role: str
    permission: str
    assigned: bool
    assignment: Assignment
    in_scope: bool
    expected: bool

    @property
    def id(self) -> str:
        state = "assigned" if self.assigned else "unassigned"
        where = "P1" if self.in_scope else "P2"
        verdict = "allow" if self.expected else "deny"
        return f"{self.role}-{self.permission}-{state}-{self.assignment}-{where}-{verdict}"


def matrix_cases(
    role_permissions: Mapping[str, Iterable[str]],
    permissions: Iterable[str],
    *,
    assignments: Sequence[Assignment] = ASSIGNMENTS,
) -> list[MatrixCase]:
    """Every combination, in a stable order (role, permission, state, scope, resource)."""
    granted = {role: frozenset(codes) for role, codes in role_permissions.items()}
    codes = sorted(set(permissions))
    out: list[MatrixCase] = []
    for role in sorted(granted):
        for permission in codes:
            holds = permission in granted[role]
            for assigned in (True, False):
                for assignment in assignments:
                    for in_scope in (True, False):
                        scope_ok = assignment == "tenant" or in_scope
                        out.append(
                            MatrixCase(
                                role,
                                permission,
                                assigned,
                                assignment,
                                in_scope,
                                expected=assigned and holds and scope_ok,
                            )
                        )
    return out
