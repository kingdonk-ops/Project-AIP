"""``ModuleManifest``: the validated contents of a module's ``manifest.toml``."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

MODULE_ID_PATTERN = r"^[a-z][a-z0-9_]*$"
"""Module ids are Python package names in snake_case (kebab-case is not allowed)."""

ModuleId = Annotated[str, Field(pattern=MODULE_ID_PATTERN)]


class EventRef(BaseModel):
    """A versioned domain event, e.g. ``widget.created`` v1."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Annotated[str, Field(min_length=1)]
    version: Annotated[int, Field(ge=1)]


class ModuleManifest(BaseModel):
    """Declares a module's identity, dependencies and published surface."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ModuleId
    context: Annotated[str, Field(min_length=1)]
    depends_on: list[ModuleId] = Field(default_factory=list[str])
    permissions: list[str] = Field(default_factory=list[str])
    events: list[EventRef] = Field(default_factory=list[EventRef])
    subscribes: list[EventRef] = Field(default_factory=list[EventRef])
    settings: list[str] = Field(default_factory=list[str])
    term_keys: list[str] = Field(default_factory=list[str])

    @classmethod
    def from_toml(cls, path: str | Path) -> ModuleManifest:
        """Load and validate a ``manifest.toml`` file."""
        with Path(path).open("rb") as fh:
            data = tomllib.load(fh)
        return cls.model_validate(data)
