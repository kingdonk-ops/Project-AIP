"""SECURITY-11 Part C (review 11 M6): the demo deploy is gated, scanned, signed and SHA-pinned."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
DEPLOY = WORKFLOWS / "deploy-coolify.yml"
SECURITY = WORKFLOWS / "security.yml"
DEMO_IMAGES = {
    "aip-api",
    "aip-migrator",
    "aip-web-demo",
    "aip-postgres-demo",
    "aip-keycloak-demo",
}


@pytest.fixture(scope="module")
def workflow() -> dict[Any, Any]:
    return yaml.safe_load(DEPLOY.read_text())


def _steps(workflow: dict[Any, Any], job: str) -> list[dict[str, Any]]:
    return workflow["jobs"][job]["steps"]


def _run(workflow: dict[Any, Any], job: str, name_part: str) -> str:
    step = next(s for s in _steps(workflow, job) if name_part in s.get("name", ""))
    return step["run"]


def test_every_action_is_pinned_by_commit_sha() -> None:
    uses = re.findall(r"^\s*(?:-\s+)?uses:\s*(\S+)", DEPLOY.read_text(), flags=re.M)
    assert uses
    unpinned = [u for u in uses if not re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", u)]
    assert unpinned == []


def test_the_deploy_runs_only_after_a_green_security_run_on_main(workflow: dict[Any, Any]) -> None:
    on = workflow[True]  # PyYAML reads the `on:` key as a boolean
    assert "push" not in on and "pull_request" not in on
    assert on["workflow_run"] == {
        "workflows": ["security"],
        "types": ["completed"],
        "branches": ["main"],
    }
    condition = workflow["jobs"]["images"]["if"]
    assert "github.event.workflow_run.conclusion == 'success'" in condition
    assert "github.event.workflow_run.event == 'push'" in condition
    assert "github.ref == 'refs/heads/main'" in condition  # a manual run only from main
    assert workflow["jobs"]["deploy"]["needs"] == "images"
    # It builds and deploys the commit security passed, not whatever main is now.
    assert workflow["env"]["SHA"] == "${{ github.event.workflow_run.head_sha || github.sha }}"
    for job in ("images", "deploy"):
        checkout = next(
            s for s in _steps(workflow, job) if "actions/checkout@" in s.get("uses", "")
        )
        assert checkout["with"]["ref"] == "${{ env.SHA }}", job


def test_all_five_images_are_scanned_and_sboms_made_before_anything_is_pushed(
    workflow: dict[Any, Any],
) -> None:
    names = [s.get("name", "") for s in _steps(workflow, "images")]
    build = _run(workflow, "images", "Build the demo images")
    assert set(re.findall(r"^\s*build (aip-[a-z-]+) ", build, flags=re.M)) == DEMO_IMAGES
    assert "docker push" not in build
    scan = _run(workflow, "images", "Trivy scan")
    assert "--exit-code 1" in scan and "--ignorefile /cfg/vuln-exceptions.txt" in scan
    assert '< "$RUNNER_TEMP/images.txt"' in scan and "exit $fail" in scan
    sbom = _run(workflow, "images", "SBOM")
    assert '< "$RUNNER_TEMP/images.txt"' in sbom and "cyclonedx-json" in sbom
    push = names.index(next(n for n in names if n.startswith("Push")))
    assert names.index(next(n for n in names if n.startswith("Trivy"))) < push
    assert names.index(next(n for n in names if n.startswith("SBOM"))) < push
    assert names.index(next(n for n in names if n.startswith("Log in"))) < push


def test_the_pushed_digests_are_signed_with_the_real_key_and_verified(
    workflow: dict[Any, Any],
) -> None:
    push = _run(workflow, "images", "Push the scanned images")
    # Registry digests of the pushed repository, not local image ids.
    assert "docker buildx imagetools inspect --format '{{.Manifest.Digest}}'" in push
    assert 'echo "$REGISTRY/$name@$digest" >> evidence/image-digests.txt' in push
    sign = _run(workflow, "images", "Sign and verify")
    assert 'if [ -z "$COSIGN_PRIVATE_KEY" ]; then' in sign
    assert "exit 1" in sign and "ephemeral" not in sign and "generate-key-pair" not in sign
    assert "cosign sign --yes --key /keys/cosign.key" in sign
    assert "cosign verify --key /keys/cosign.pub" in sign
    assert "< evidence/image-digests.txt" in sign


def test_security_fails_on_main_without_the_cosign_key() -> None:
    text = SECURITY.read_text()
    assert 'elif [ "$GITHUB_REF" = "refs/heads/main" ]; then' in text
    branch = text.split('elif [ "$GITHUB_REF" = "refs/heads/main" ]; then', 1)[1].split("else", 1)[
        0
    ]
    assert "exit 1" in branch
