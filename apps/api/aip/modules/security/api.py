"""Published interface of the security module.

Other modules may import only this file. Keep it small and stable. SECURITY-02 ships only the
schema; the operations other modules use (evidence collection, the data map) arrive with
SECURITY-03 to SECURITY-06.
"""

from __future__ import annotations

from typing import Protocol


class ModuleApi(Protocol):
    """The operations security offers to other modules."""


def get_api() -> ModuleApi:
    """Return the security module's published interface."""
    raise NotImplementedError
