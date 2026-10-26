"""The scan pipeline reducer (UPLOADS-02 step 3): run the stages in order, fail closed.

The stages run size -> magic bytes -> ratio/pixel caps -> ClamAV. The first non-``pass`` stops the
pipeline: a ``fail`` rejects the upload, an ``error`` (a scan that could not complete) is retried by
the worker and, on the last attempt, rejected as ``scan_error``. A ``ClamdError`` is caught and
recorded as a ``clamav``/``error`` stage, so the reducer always returns the stages it ran and never
lets an incomplete scan pass. Every returned ``StageResult`` becomes one ``scan_results`` row.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .caps import ratio_cap, size_cap
from .clamav_client import ClamdError, ClamdSettings, clamav_stage
from .magic_bytes import HEAD_BYTES, check_magic_bytes
from .types import Outcome, StageResult

__all__ = ["ScanInput", "ScanVerdict", "run_scan"]


@dataclass(frozen=True)
class ScanInput:
    """The object and the declared facts the stages check it against."""

    data: bytes
    declared_mime: str
    declared_size: int
    platform_max: int


@dataclass(frozen=True)
class ScanVerdict:
    """The pipeline's outcome, the detected type, and one result per stage that ran."""

    outcome: Outcome
    detected_mime: str | None
    results: list[StageResult] = field(default_factory=list)


async def run_scan(scan: ScanInput, clamd: ClamdSettings) -> ScanVerdict:
    """Run the stages in order, stopping at the first non-``pass``; fail closed on a scan error."""
    results: list[StageResult] = []
    detected: str | None = None

    size = size_cap(len(scan.data), scan.declared_size, scan.platform_max)
    results.append(size)
    if size.outcome != "pass":
        return ScanVerdict(size.outcome, detected, results)

    magic = check_magic_bytes(scan.data[:HEAD_BYTES], scan.declared_mime)
    results.append(magic)
    detected = magic.detail.get("detected") or None
    if magic.outcome != "pass":
        return ScanVerdict(magic.outcome, detected, results)

    ratio = ratio_cap(scan.data, detected or "")
    results.append(ratio)
    if ratio.outcome != "pass":
        return ScanVerdict(ratio.outcome, detected, results)

    # ClamAV is the only stage that reaches out: a scan that cannot complete fails closed as an
    # ``error`` stage (the worker retries, and the last attempt rejects), never as a pass.
    try:
        clam = await clamav_stage(scan.data, clamd)
    except ClamdError as exc:
        clam = StageResult("clamav", "error", {"error": str(exc)})
    results.append(clam)
    return ScanVerdict(clam.outcome, detected, results)
