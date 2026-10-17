"""``ModuleManifest``: the validated contents of a module's ``manifest.toml``."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

MODULE_ID_PATTERN = r"^[a-z][a-z0-9_]*$"
"""Module ids are Python package names in snake_case (kebab-case is not allowed)."""

ModuleId = Annotated[str, Field(pattern=MODULE_ID_PATTERN)]


class EventRef(BaseModel):
    """A versioned domain event, e.g. ``widget.created`` v1."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Annotated[str, Field(min_length=1)]
    version: Annotated[int, Field(ge=1)]


class PermissionEntry(BaseModel):
    """A ``[[permissions]]`` table: one atomic permission the module declares (ACCESS-01).

    The code format and namespace are checked when the catalogue is built
    (``aip.platform.access.catalogue``), so the error can name the module.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: Annotated[str, Field(min_length=1)]
    description: Annotated[str, Field(min_length=1)]
    privileged: bool = False


class ScheduleEntry(BaseModel):
    """A ``[[schedules]]`` table (OPS-13): a registered job the platform triggers on ``cron``.

    The trigger (a Coolify scheduled task, EventBridge Scheduler in AWS) runs
    ``python -m aip.modules.ops.schedule enqueue <job> --all-tenants``; ``period`` sets the
    idempotency window, so a trigger that fires twice in one period enqueues once.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    job: Annotated[str, Field(min_length=1)]
    cron: Annotated[str, Field(pattern=r"^\S+( \S+){4}$")]
    period: Literal["hour", "day", "week", "month"] = "month"


class ModuleManifest(BaseModel):
    """Declares a module's identity, dependencies and published surface."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ModuleId
    context: Annotated[str, Field(min_length=1)]
    depends_on: list[ModuleId] = Field(default_factory=list[str])
    permissions: list[PermissionEntry] = Field(default_factory=list[PermissionEntry])
    permission_namespaces: list[ModuleId] | None = None
    events: list[EventRef] = Field(default_factory=list[EventRef])
    subscribes: list[EventRef] = Field(default_factory=list[EventRef])
    settings: list[str] = Field(default_factory=list[str])
    term_keys: list[str] = Field(default_factory=list[str])
    schedules: list[ScheduleEntry] = Field(default_factory=list[ScheduleEntry])

    @property
    def namespaces(self) -> tuple[str, ...]:
        """The first permission-code segments this module owns (default: its own id)."""
        if self.permission_namespaces is None:
            return (self.id,)
        return tuple(self.permission_namespaces)

    @classmethod
    def from_toml(cls, path: str | Path) -> ModuleManifest:
        """Load and validate a ``manifest.toml`` file."""
        with Path(path).open("rb") as fh:
            data = tomllib.load(fh)
        return cls.model_validate(data)
