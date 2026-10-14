"""Published interface of the terms module.

Other modules may import only this file. Keep it small and stable.
"""

from __future__ import annotations

from typing import Protocol


class ModuleApi(Protocol):
    """The operations terms offers to other modules."""


def get_api() -> ModuleApi:
    """Return the terms module's published interface."""
    raise NotImplementedError
