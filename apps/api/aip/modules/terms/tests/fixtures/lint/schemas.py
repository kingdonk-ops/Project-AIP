"""TERMS-07 fixture: a schema with one raw label default (line 7). Never imported."""

from pydantic import BaseModel


class ChangeOut(BaseModel):
    label: str = "Variation"
    code: str = "Variation"  # not a label field: not flagged
    title: str | None = None
