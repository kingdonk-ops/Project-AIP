"""The upload scan pipeline (UPLOADS-02).

After an upload is confirmed, the ``uploads.scan`` job streams the quarantine object once and runs
the stages in order — size cap, magic bytes, decompression/pixel caps, then ClamAV — writing one
``scan_results`` row per stage and stopping at the first ``fail`` or ``error``. Only a clean object
is released into tenant storage; every error fails closed. This package holds the stage logic; the
reducer, the ClamAV client and the release step are added alongside.
"""

from __future__ import annotations

from .types import Outcome, StageResult

__all__ = ["Outcome", "StageResult"]
