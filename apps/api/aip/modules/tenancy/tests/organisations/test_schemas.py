"""TENANCY-03 unit tests: organisation request validation (no database)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aip.modules.tenancy.organisations.schemas import OrganisationCreate, OrganisationUpdate


def test_the_three_types_are_accepted() -> None:
    for kind in ("owner", "client", "subcontractor"):
        assert OrganisationCreate.model_validate({"name": "X", "type": kind}).org_type == kind


def test_type_other_fails_validation() -> None:
    with pytest.raises(ValidationError):
        OrganisationCreate.model_validate({"name": "X", "type": "other"})


def test_names_are_trimmed_and_must_not_be_blank() -> None:
    assert OrganisationCreate.model_validate({"name": "  Rio Tinto ", "type": "client"}).name == (
        "Rio Tinto"
    )
    with pytest.raises(ValidationError):
        OrganisationCreate.model_validate({"name": "   ", "type": "client"})


def test_an_update_cannot_null_the_name_type_or_status() -> None:
    for field in ("name", "type", "status"):
        with pytest.raises(ValidationError):
            OrganisationUpdate.model_validate({"syncVersion": 1, field: None})
    patch = OrganisationUpdate.model_validate({"syncVersion": 1, "registrationNumber": None})
    assert patch.changes(exclude=frozenset({"sync_version"})) == {"registration_number": None}
