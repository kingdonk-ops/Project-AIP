"""ACCESS-02 unit tests: level expansion and the default roles built from the access matrix."""

from __future__ import annotations

import logging

import pytest

from aip.modules.access.roles.default_roles import (
    MATRIX,
    ROLE_CODES,
    Level,
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

# The real inspections codes (INSPECTIONS-02, INSPECTIONS-03).
ITP = [
    ("inspection.view", "inspections"),
    ("inspection.create", "inspections"),
    ("inspection.respond", "inspections"),
    ("itp.sign", "inspections"),
    ("itp.manage", "inspections"),
    ("itp.waive", "inspections"),
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


def test_inspector_signs_and_supervisor_creates_inspections() -> None:
    roles = default_permissions(INSPECTIONS)
    assert "inspections.hold_point.sign" in roles["inspector"]
    assert roles["supervisor"] == {"inspections.inspection.read", "inspections.inspection.create"}
    assert "inspections.inspection.approve" in roles["qaqc_manager"]
    assert "inspections.hold_point.sign" in roles["client_reviewer"]
    # Client Reviewer: read-only plus sign-off, never create or edit (owner, 2026-10-10).
    assert roles["client_reviewer"] == {
        "inspections.inspection.read",
        "inspections.inspection.approve",
        "inspections.hold_point.sign",
    }
    assert roles["auditor"] == {"inspections.inspection.read"}


def test_itp_permissions_follow_the_quality_hierarchy() -> None:
    # Owner, 2026-11-02: QA/QC Manager (lead inspector) sets up and waives ITP steps, the
    # inspector signs them, the supervisor (trade lead) creates and answers but does not sign.
    roles = default_permissions(ITP)
    assert roles["qaqc_manager"] == {code for code, _ in ITP}
    assert roles["inspector"] == {
        "inspection.view",
        "inspection.create",
        "inspection.respond",
        "itp.sign",
    }
    assert roles["supervisor"] == {"inspection.view", "inspection.create", "inspection.respond"}
    assert "itp.manage" not in roles["project_manager"]
    assert roles["client_reviewer"] == {"inspection.view", "itp.sign"}
    assert roles["auditor"] == {"inspection.view"}


def test_there_are_eleven_roles_and_every_matrix_row_has_a_level_for_each() -> None:
    assert len(ROLE_CODES) == 11
    assert all(len(levels) == 11 for levels in MATRIX.values())
    assert MATRIX["inspections"][ROLE_CODES.index("inspector")] == "approve"


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


def test_default_roles_never_get_operator_only_codes() -> None:
    catalogue = [
        ("platform.tenants.manage", "ops"),
        ("ops.job.view", "ops"),
        ("project.view", "projects"),
    ]
    granted = default_permissions(catalogue)
    assert not any(c.startswith("platform.") for codes in granted.values() for c in codes)


# --- ACCESS-07: `move` at edit, `invite` at approve (ADR 0027 amendment) ----------------------

ASSETS = [
    ("asset.view", "assets"),
    ("asset.create", "assets"),
    ("asset.update", "assets"),
    ("asset.move", "assets"),
    ("asset.delete", "assets"),
]

PORTAL = [
    ("portal.user.view", "portal"),
    ("portal.user.invite", "portal"),
    ("portal.user.suspend", "portal"),
    ("portal.grant.manage", "portal"),
]


def test_move_is_an_edit_verb_and_invite_an_approve_verb() -> None:
    verbs = ["read", "create", "update", "move", "invite", "manage"]
    assert expand_level("create", verbs) == ["read", "create"]
    assert expand_level("edit", verbs) == ["read", "create", "update", "move"]
    assert expand_level("approve", verbs) == ["read", "create", "update", "move", "invite"]


def test_roles_that_edit_assets_can_move_them_and_creators_cannot() -> None:
    roles = default_permissions(ASSETS)
    for role in ("tenant_admin", "project_manager", "qaqc_manager", "supervisor"):
        assert "asset.move" in roles[role], role
    assert roles["inspector"] == {"asset.view", "asset.create"}
    assert roles["field_worker"] == {"asset.view"}
    assert roles["client_reviewer"] == {"asset.view"}


def test_project_managers_can_invite_portal_clients() -> None:
    roles = default_permissions(PORTAL)
    assert roles["project_manager"] == {"portal.user.view", "portal.user.invite"}
    assert roles["tenant_admin"] == {code for code, _ in PORTAL}
    # The edit level (QA/QC manager, document controller) sees portal users but cannot invite.
    assert roles["qaqc_manager"] == {"portal.user.view"}
    assert roles["document_controller"] == {"portal.user.view"}


def test_client_reviewer_approve_level_is_sign_off_only_not_invite() -> None:
    levels: list[Level] = ["none"] * len(ROLE_CODES)
    levels[ROLE_CODES.index("client_reviewer")] = "approve"
    catalogue = [*PORTAL, ("portal.case.approve", "portal"), ("portal.case.sign", "portal")]
    roles = default_permissions(catalogue, {"portal": tuple(levels)})
    assert roles["client_reviewer"] == {
        "portal.user.view",
        "portal.case.approve",
        "portal.case.sign",
    }
