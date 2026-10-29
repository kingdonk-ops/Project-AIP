"""Merge-queue stand-in: auto-merge PRs behind main get main merged in, and CI re-runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "auto-update-prs.yml"


@pytest.fixture(scope="module")
def workflow() -> dict[Any, Any]:
    return yaml.safe_load(WORKFLOW.read_text())


def _script(workflow: dict[Any, Any]) -> str:
    return workflow["jobs"]["update"]["steps"][0]["run"]


def test_runs_when_main_moves_and_on_demand(workflow: dict[Any, Any]) -> None:
    on = workflow[True]  # PyYAML reads the `on:` key as a boolean
    assert on["push"] == {"branches": ["main"]}
    assert "workflow_dispatch" in on
    assert "pull_request" not in on and "pull_request_target" not in on
    assert workflow["concurrency"]["cancel-in-progress"] is True


def test_pushes_with_a_token_that_triggers_ci_not_github_token(workflow: dict[Any, Any]) -> None:
    env = workflow["jobs"]["update"]["steps"][0]["env"]
    assert env["GH_TOKEN"] == "${{ secrets.PR_UPDATE_TOKEN }}"
    assert 'if [ -z "$GH_TOKEN" ]' in _script(workflow)  # fails loudly without it


def test_only_touches_opted_in_same_repo_ready_prs(workflow: dict[Any, Any]) -> None:
    script = _script(workflow)
    assert ".autoMergeRequest != null" in script
    assert "(.isDraft | not)" in script
    assert "(.isCrossRepository | not)" in script
    assert "expected_head_sha" in script  # never overwrites a head that moved since listing


def test_no_expression_is_inlined_into_the_script(workflow: dict[Any, Any]) -> None:
    assert "${{" not in _script(workflow)
