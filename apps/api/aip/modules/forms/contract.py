"""The form-template JSON Schema contract (FORMS-01).

The lint validates an uploaded revision ``schema`` against
``packages/contracts/forms/form-template.schema.json``. That tree is not shipped in the runtime
image (only ``/opt/venv``, the migrations and ``config/terms`` are), so — like ``terms`` bakes its
lint findings — a byte-identical copy lives in this package at ``data/form-template.schema.json``
and is loaded from there. ``tests/test_contract_parity`` keeps the two in step.

Loading is lazy and cached, so importing the module never touches the filesystem (the ITEMTYPES-01
image crash was an import-time contract read) and the schema is parsed once per process.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

__all__ = ["CONTRACT_PATH", "contract_schema", "validator"]

CONTRACT_PATH = Path(__file__).resolve().parent / "data" / "form-template.schema.json"


@cache
def contract_schema() -> dict[str, Any]:
    """The parsed form-template JSON Schema (Draft 2020-12), read once per process."""
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


@cache
def validator() -> Draft202012Validator:
    """A validator for the contract; its schema is checked once when first built."""
    schema = contract_schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)
