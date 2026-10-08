"""Published interface of the identity module.

Other modules may import only this file. Keep it small and stable.
"""

from __future__ import annotations

from typing import Protocol


class ModuleApi(Protocol):
    """The operations identity offers to other modules."""


def get_api() -> ModuleApi:
    """Return the identity module's published interface."""
    raise NotImplementedError
