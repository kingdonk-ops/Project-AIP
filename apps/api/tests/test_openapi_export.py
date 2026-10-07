"""Tests for tools/codegen/export_openapi.py (STACK-03)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "codegen" / "export_openapi.py"


def export(out: Path) -> bytes:
    subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.read_bytes()


def test_export_is_valid_json_with_health_path(tmp_path: Path) -> None:
    raw = export(tmp_path / "openapi.json")
    spec = json.loads(raw)
    assert "/api/v1/health" in spec["paths"]
    assert raw.endswith(b"}\n")


def test_two_exports_are_byte_identical(tmp_path: Path) -> None:
    first = export(tmp_path / "a.json")
    second = export(tmp_path / "b.json")
    assert first == second


def test_export_is_sorted_with_two_space_indent(tmp_path: Path) -> None:
    raw = export(tmp_path / "openapi.json")
    spec = json.loads(raw)
    expected = json.dumps(spec, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    assert raw.decode("utf-8") == expected


def test_operation_ids_are_tag_and_function_name(tmp_path: Path) -> None:
    spec = json.loads(export(tmp_path / "openapi.json"))
    health = spec["paths"]["/api/v1/health"]["get"]
    assert health["operationId"] == "platform_health"
    schema_ref = health["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert schema_ref == "#/components/schemas/HealthResponse"
    modules = spec["paths"]["/api/v1/platform/modules"]["get"]
    assert modules["operationId"] == "platform_list_modules"


def test_committed_openapi_matches_export(tmp_path: Path) -> None:
    committed = ROOT / "packages" / "api-client" / "openapi.json"
    assert committed.read_bytes() == export(tmp_path / "openapi.json")
