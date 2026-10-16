"""DATABASE-07 (carried from the DATABASE-02 security review): only ``with_tenant`` sets the tenant.

``aip.platform.db.session`` sets ``app.tenant_id`` transaction-locally for every request and job.
Code holding such a connection could otherwise call ``set_config('app.tenant_id', other, true)``,
``SET [LOCAL] app.tenant_id`` or ``RESET app.tenant_id`` mid-transaction and read another tenant's
rows. This scans every non-test source under ``aip/`` for those statements. Reading the setting
(``current_setting('app.tenant_id')`` in RLS policies and functions) is fine.
"""

from __future__ import annotations

import re
from pathlib import Path

AIP_DIR = Path(__file__).resolve().parents[2] / "aip"

CHANGES_TENANT = re.compile(
    r"set_config\(\s*['\"]app\.tenant_id['\"]"
    r"|\bSET\s+(?:LOCAL\s+|SESSION\s+)?app\.tenant_id\b"
    r"|\bRESET\s+app\.tenant_id\b",
    re.IGNORECASE,
)

# path (relative to aip/) -> why it may set the tenant itself.
ALLOWED = {
    "platform/db/session.py": "with_tenant and the other session helpers: the one place it is set.",
    "modules/tenancy/seed.py": (
        "The fixture-tenant seed (dev/CI only, refuses production) writes as the table owner, which"
        " FORCE RLS also binds, so it sets each fixture tenant's id for its own row."
    ),
}


def offenders(root: Path = AIP_DIR) -> list[str]:
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if "/tests/" in f"/{rel}" or "__pycache__" in path.parts or rel in ALLOWED:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if CHANGES_TENANT.search(line):
                found.append(f"{rel}:{number}: {line.strip()}")
    return found


def test_only_the_session_helpers_set_the_tenant() -> None:
    assert offenders() == []


def test_every_allowed_file_exists_and_has_a_reason() -> None:
    for rel, reason in ALLOWED.items():
        assert (AIP_DIR / rel).is_file(), rel
        assert reason.strip(), rel


def test_the_scan_catches_each_form(tmp_path: Path) -> None:
    module = tmp_path / "modules" / "x" / "repository.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "a = text(\"SELECT set_config('app.tenant_id', :t, true)\")\n"
        "b = \"SET LOCAL app.tenant_id = 'x'\"\n"
        'c = "reset app.tenant_id"\n'
        "d = \"SELECT current_setting('app.tenant_id', true)\"\n",
        encoding="utf-8",
    )
    test_file = tmp_path / "modules" / "x" / "tests" / "test_x.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "a = \"SELECT set_config('app.tenant_id', 'x', true)\"\n", encoding="utf-8"
    )
    assert [o.split(": ")[0] for o in offenders(tmp_path)] == [
        "modules/x/repository.py:1",
        "modules/x/repository.py:2",
        "modules/x/repository.py:3",
    ]
