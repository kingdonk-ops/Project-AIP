"""HTTP routes for terms, mounted under ``/api/v1``.

``GET /terms/coverage`` (TERMS-07) returns the hard-coded label report the API image build baked
in (``python lint.py --report-only --out aip/modules/terms/data/lint_findings.json``, see
``apps/api/Dockerfile``) with the build commit. ``TERMS_LINT_FINDINGS`` points at another file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import TypeAdapter

from aip.modules.terms.schemas import LintFindingOut, TermsCoverage
from aip.platform.access import requires

__all__ = ["BAKED_FINDINGS", "FINDINGS_ENV", "router"]

FINDINGS_ENV = "TERMS_LINT_FINDINGS"
BAKED_FINDINGS = Path(__file__).resolve().parent / "data" / "lint_findings.json"
_FINDINGS = TypeAdapter(list[LintFindingOut])

router = APIRouter(tags=["terms"])


@router.get(
    "/terms/coverage",
    operation_id="terms_coverage",
    response_model=TermsCoverage,
    dependencies=[Depends(requires("terms.coverage.read"))],
)
async def coverage() -> TermsCoverage:
    path = Path(os.environ.get(FINDINGS_ENV) or BAKED_FINDINGS)
    commit = os.environ.get("GIT_SHA") or "unknown"
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return TermsCoverage(commit=commit, available=False, findings=[])
    findings = _FINDINGS.validate_python(json.loads(raw))
    return TermsCoverage(commit=commit, available=True, findings=findings)
