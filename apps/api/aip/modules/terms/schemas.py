"""Pydantic request/response models for terms."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

__all__ = ["LintFindingOut", "TermsCoverage"]


class LintFindingOut(BaseModel):
    """One raw label found by the TERMS-07 scanner (lines and columns 1-based)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)

    file: str
    line: int
    column: int
    term: str
    suggested_key: str | None


class TermsCoverage(BaseModel):
    """Body of GET /api/v1/terms/coverage: the findings baked into the running build."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)

    commit: str
    available: bool  # false when this build carries no findings file (a local dev run)
    findings: list[LintFindingOut]
