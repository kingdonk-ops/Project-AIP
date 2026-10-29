"""SECURITY-08: the security gate scans the same five images as the deploy, daily, and reports.

The regression this guards against: `security` used to build and scan only aip-api and aip-web,
while `deploy-coolify` scans five images, so a CVE in the other three passed every PR and only
failed after merge. Both gates now go through tools/ci/scan_images.sh.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
SECURITY = WORKFLOWS / "security.yml"
DEPLOY = WORKFLOWS / "deploy-coolify.yml"
SCAN_SCRIPT = ROOT / "tools" / "ci" / "scan_images.sh"
DEMO_IMAGES = {
    "aip-api",
    "aip-migrator",
    "aip-web-demo",
    "aip-postgres-demo",
    "aip-keycloak-demo",
}


@pytest.fixture(scope="module")
def workflow() -> dict[Any, Any]:
    return yaml.safe_load(SECURITY.read_text())


def _steps(workflow: dict[Any, Any], job: str) -> list[dict[str, Any]]:
    return workflow["jobs"][job]["steps"]


def _run(workflow: dict[Any, Any], job: str, name_part: str) -> str:
    step = next(s for s in _steps(workflow, job) if name_part in s.get("name", ""))
    return step["run"]


def test_images_job_builds_and_scans_the_five_demo_images_via_the_shared_recipe(
    workflow: dict[Any, Any],
) -> None:
    assert "scan_images.sh build" in _run(workflow, "images", "Build the demo image set")
    assert "scan_images.sh scan" in _run(workflow, "images", "Trivy image scan of every demo image")
    # The five images live in the shared script — the single source of truth for both gates.
    script = SCAN_SCRIPT.read_text()
    assert set(re.findall(r"^\s*build_one (aip-[a-z-]+) ", script, flags=re.M)) == DEMO_IMAGES


def test_both_gates_call_the_same_shared_recipe() -> None:
    assert SCAN_SCRIPT.exists()
    assert "scan_images.sh" in SECURITY.read_text()
    assert "scan_images.sh" in DEPLOY.read_text()


def test_the_strip_test_and_board_only_skip_still_work(workflow: dict[Any, Any]) -> None:
    names = [s.get("name", "") for s in _steps(workflow, "images")]
    assert any("Production strip" in n for n in names)
    assert (
        workflow["jobs"]["images"]["if"]
        == "${{ always() && needs.detect.outputs.board_only != 'true' }}"
    )


def test_the_scan_runs_daily(workflow: dict[Any, Any]) -> None:
    on = workflow[True]  # PyYAML reads the `on:` key as a boolean
    assert [s["cron"] for s in on["schedule"]] == ["17 19 * * *"]


def test_schedule_failure_opens_one_labelled_issue_with_minimal_permissions(
    workflow: dict[Any, Any],
) -> None:
    job = workflow["jobs"]["report-scan-failure"]
    assert set(job["needs"]) == {"images", "deps", "secrets"}
    condition = job["if"]
    assert "github.event_name == 'schedule'" in condition
    assert "result == 'failure'" in condition  # only when a scan actually failed
    # Minimal permissions: write issues (contents:read is just for the checkout), nothing more.
    assert job["permissions"] == {"contents": "read", "issues": "write"}
    body = " ".join(s.get("run", "") for s in job["steps"])
    assert "Daily security scan failing" in body  # one fixed title, so it updates not duplicates
    assert "--label security" in body
    assert "gh issue create" in body and "gh issue edit" in body  # open OR update
    assert "github.run_id" in yaml.safe_dump(job)  # the body/comment link the run


def test_new_actions_in_the_report_job_are_pinned_by_sha(workflow: dict[Any, Any]) -> None:
    uses = [s["uses"] for s in _steps(workflow, "report-scan-failure") if "uses" in s]
    assert uses
    unpinned = [u for u in uses if not re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", u)]
    assert unpinned == []
