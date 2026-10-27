"""The schema baked into the forms package must equal the shared contract (FORMS-01).

The runtime image ships only the package, so the lint loads the baked copy; the web client and
other tooling use ``packages/contracts/forms/form-template.schema.json``. This keeps them identical.
"""

from __future__ import annotations

import json

from aip.modules.forms.contract import CONTRACT_PATH
from aip.platform.db.migrator import repo_root


def test_baked_contract_matches_the_shared_contract() -> None:
    shared = repo_root() / "packages" / "contracts" / "forms" / "form-template.schema.json"
    assert json.loads(CONTRACT_PATH.read_text(encoding="utf-8")) == json.loads(
        shared.read_text(encoding="utf-8")
    )
