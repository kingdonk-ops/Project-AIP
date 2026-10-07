"""Published interface of the __module__ module.

Other modules may import only this file. Keep it small and stable.
"""

from __future__ import annotations

from typing import Protocol


class ModuleApi(Protocol):
    """The operations __module__ offers to other modules."""


def get_api() -> ModuleApi:
    """Return the __module__ module's published interface."""
    raise NotImplementedError
