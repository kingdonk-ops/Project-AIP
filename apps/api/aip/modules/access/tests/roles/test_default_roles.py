"""ACCESS-02 unit tests: level expansion and the default roles built from the access matrix."""

from __future__ import annotations

import logging

import pytest

from aip.modules.access.roles.default_roles import (
    MATRIX,
    ROLE_CODES,
    default_permissions,
    expand_level,
)

INSPECTIONS = [
    ("inspections.inspection.read", "inspections"),
    ("inspections.inspection.create", "inspections"),
    ("inspections.inspection.update", "inspections"),
    ("inspections.inspection.approve", "inspections"),
    ("inspections.hold_point.sign", "inspections"),
]


def test_expand_level_is_cumulative_and_keeps_order() -> None:
    verbs = ["read", "create", "update", "delete", "approve", "sign", "manage"]
    assert expand_level("approve", verbs) == [
        "read",
        "create",
        "update",
        "delete",
        "approve",
        "sign",
    ]
    assert expand_level("view", verbs) == ["read"]
    assert expand_level("none", verbs) == []
    assert expand_level("admin", [*verbs, "export"]) == [*verbs, "export"]


def test_an_unknown_verb_needs_admin() -> None:
    assert expand_level("approve", ["purge"]) == []
    assert expand_level("admin", ["purge"]) == ["purge"]


def test_inspector_creates_inspections_but_cannot_approve() -> None:
    roles = default_permissions(INSPECTIONS)
    assert roles["inspector"] == {"inspections.inspection.read", "inspections.inspection.create"}
    assert "inspections.inspection.approve" in roles["qaqc_manager"]
    assert "inspections.hold_point.sign" in roles["client_reviewer"]
    # Client Reviewer: read-only plus sign-off, never create or edit (owner, 2026-10-10).
    assert roles["client_reviewer"] == {
        "inspections.inspection.read",
        "inspections.inspection.approve",
        "inspections.hold_point.sign",
    }
    assert roles["auditor"] == {"inspections.inspection.read"}


def test_there_are_eleven_roles_and_every_matrix_row_has_a_level_for_each() -> None:
    assert len(ROLE_CODES) == 11
    assert all(len(levels) == 11 for levels in MATRIX.values())
    assert MATRIX["inspections"][ROLE_CODES.index("inspector")] == "create"


def test_modules_without_catalogue_entries_are_skipped_with_a_log_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        roles = default_permissions([("project.view", "projects")])
    assert "inspections" in caplog.text
    assert all(codes == {"project.view"} for codes in roles.values())


def test_the_real_catalogue_gives_tenant_admin_role_management() -> None:
    catalogue = [
        ("access.role.read", "access"),
        ("access.role.manage", "access"),
        ("access.role_assignment.manage", "access"),
        ("project.view", "projects"),
        ("project.archive", "projects"),
    ]
    roles = default_permissions(catalogue)
    assert {"access.role.manage", "access.role_assignment.manage"} <= roles["tenant_admin"]
    assert roles["project_manager"] == {"access.role.read", "project.view", "project.archive"}
    assert roles["inspector"] == {"project.view"}
