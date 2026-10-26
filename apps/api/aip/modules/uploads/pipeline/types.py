"""Shared result type for the scan stages (UPLOADS-02)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# The stage codes mirror the ``scan_results.stage`` check constraint.
Stage = Literal["size_cap", "magic_bytes", "ratio_cap", "clamav", "rescan"]
# ``pass`` continues, ``fail`` rejects the upload, ``error`` throws so the job retries (fail-closed)

Outcome = Literal["pass", "fail", "error"]

__all__ = ["Outcome", "Stage", "StageResult"]


@dataclass(frozen=True)
class StageResult:
    """One stage's verdict, written as one ``scan_results`` row."""

    stage: Stage
    outcome: Outcome
    detail: dict[str, Any] = field(default_factory=dict)
