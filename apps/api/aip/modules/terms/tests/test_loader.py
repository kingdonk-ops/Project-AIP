"""TERMS-01: the en-AU default dictionary, its validation and the idempotent loader.

Unit tests read dictionaries from ``tmp_path`` and need no database. Integration tests load into a
freshly migrated database as ``aip_owner`` (``with_platform_tenant``) and assert through ``aip_app``
(``tenant_db``), so RLS applies to every assertion.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import REPO_ROOT, TenantDb

from aip.modules.terms.loader import (
    DictionaryError,
    InvalidMessageError,
    LoadResult,
    load,
    main,
    read_dictionary,
)
from aip.platform.db.session import PLATFORM_TENANT_ID, PlatformTenantError, with_platform_tenant

EN_AU = REPO_ROOT / "config" / "terms" / "en-AU"
INSUFFICIENT_PRIVILEGE = "42501"


def write(directory: Path, name: str, entries: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def shipped_key_count() -> int:
    return sum(len(json.loads(p.read_text(encoding="utf-8"))) for p in EN_AU.glob("*.json"))


# --- unit: the dictionary files ---------------------------------------------------------------


def test_unbalanced_icu_message_is_rejected_naming_the_key_and_file(tmp_path: Path) -> None:
    write(tmp_path / "en-AU", "core.json", {"record.count": {"text": "Fine"}})
    write(
        tmp_path / "en-AU",
        "inspections.json",
        {"inspection.item.count": {"text": "{count, plural, one {# item}"}},
    )
    with pytest.raises(InvalidMessageError) as caught:
        read_dictionary(tmp_path / "en-AU")
    assert caught.value.key == "inspection.item.count"
    assert caught.value.file.name == "inspections.json"
    assert "inspection.item.count" in str(caught.value)
    assert "inspections.json" in str(caught.value)


def test_internal_code_as_display_text_is_rejected(tmp_path: Path) -> None:
    write(
        tmp_path / "en-AU",
        "inspections.json",
        {"inspection.status.in_progress": {"text": "in_progress"}},
    )
    with pytest.raises(InvalidMessageError, match=r"inspection\.status\.in_progress"):
        read_dictionary(tmp_path / "en-AU")


def test_text_equal_to_its_own_key_is_rejected(tmp_path: Path) -> None:
    write(tmp_path / "en-AU", "core.json", {"record.type.defect": {"text": "record.type.defect"}})
    with pytest.raises(InvalidMessageError, match=r"record\.type\.defect"):
        read_dictionary(tmp_path / "en-AU")


def test_a_key_in_two_files_is_rejected(tmp_path: Path) -> None:
    write(tmp_path / "en-AU", "core.json", {"record.type.ncr": {"text": "NCR"}})
    write(tmp_path / "en-AU", "inspections.json", {"record.type.ncr": {"text": "NCR"}})
    with pytest.raises(DictionaryError, match=r"record\.type\.ncr"):
        read_dictionary(tmp_path / "en-AU")


def test_entries_take_module_from_file_and_locale_from_directory(tmp_path: Path) -> None:
    write(
        tmp_path / "en-AU",
        "scope_work.json",
        {
            "access.method.count": {
                "text": "{count, plural, one {# method} other {# methods}}",
                "description": "Number of access methods",
            }
        },
    )
    (entry,) = read_dictionary(tmp_path / "en-AU")
    assert (entry.key, entry.module_id, entry.locale) == (
        "access.method.count",
        "scope_work",
        "en-AU",
    )
    assert entry.description == "Number of access methods"


def test_a_bare_string_entry_is_text_without_description(tmp_path: Path) -> None:
    write(tmp_path / "en-AU", "shell.json", {"shell.nav.home": "Home"})
    (entry,) = read_dictionary(tmp_path / "en-AU")
    assert (entry.module_id, entry.text, entry.description) == ("shell", "Home", None)


def test_the_shipped_en_au_dictionary_is_valid() -> None:
    entries = read_dictionary(EN_AU)
    keys = {e.key for e in entries}
    assert len(entries) == shipped_key_count()
    assert {
        "inspection.status.completed",
        "inspection.kind.rfi",
        "itp.point_type.hold",
        "itp.step.status.waived",
        "access.method.mewp",
        "access.method.ladder",
        "record.type.work_pack",
    } <= keys
    seeded = [e for e in entries if e.module_id in {"core", "inspections", "scope_work"}]
    assert seeded, "TERMS-01 seeds core, inspections and scope_work"
    assert all(e.description for e in seeded), "every TERMS-01 default has translator context"
    rfi = next(e for e in entries if e.key == "inspection.kind.rfi")
    assert "hold point, not a request for information" in (rfi.description or "")


def test_cli_without_migrator_url_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_MIGRATOR_URL", raising=False)
    assert main([str(EN_AU)]) == 2


# --- integration: the loader and RLS on real Postgres -------------------------------------


def owner(db: TenantDb) -> str:
    """The ``aip_owner`` URL the deploy job passes as ``DATABASE_MIGRATOR_URL``."""
    return db.db.owner_url


async def term_key_count(db: TenantDb) -> int:
    async with db.with_tenant(TENANT_B_ID) as conn:
        return (await conn.execute(text("SELECT count(*) FROM term_key"))).scalar_one()


async def test_loading_twice_is_idempotent(tenant_db: TenantDb) -> None:
    n = shipped_key_count()
    assert await load(EN_AU, url=owner(tenant_db)) == LoadResult(inserted=n, updated=0, unchanged=0)
    assert await term_key_count(tenant_db) == n

    assert await load(EN_AU, url=owner(tenant_db)) == LoadResult(inserted=0, updated=0, unchanged=n)
    assert await term_key_count(tenant_db) == n


async def test_a_changed_text_or_description_is_updated(
    tenant_db: TenantDb, tmp_path: Path
) -> None:
    copy = tmp_path / "en-AU"
    shutil.copytree(EN_AU, copy)
    await load(copy, url=owner(tenant_db))

    entries = json.loads((copy / "inspections.json").read_text(encoding="utf-8"))
    entries["inspection.status.completed"]["text"] = "Complete"
    entries["inspection.status.draft"]["description"] = "Reworded context"
    write(copy, "inspections.json", entries)

    n = shipped_key_count()
    assert await load(copy, url=owner(tenant_db)) == LoadResult(
        inserted=0, updated=2, unchanged=n - 2
    )
    async with tenant_db.with_tenant(TENANT_B_ID) as conn:
        completed = await conn.execute(
            text("SELECT default_text FROM term_key WHERE key = 'inspection.status.completed'")
        )
        assert completed.scalar_one() == "Complete"


async def test_one_bad_message_aborts_the_whole_load(tenant_db: TenantDb, tmp_path: Path) -> None:
    write(tmp_path / "en-AU", "core.json", {"record.type.defect": {"text": "Defect"}})
    write(tmp_path / "en-AU", "inspections.json", {"inspection.bad": {"text": "{count, plural"}})
    with pytest.raises(InvalidMessageError, match=r"inspection\.bad"):
        await load(tmp_path / "en-AU", url=owner(tenant_db))
    assert await term_key_count(tenant_db) == 0


async def test_platform_rows_are_readable_by_a_tenant(tenant_db: TenantDb) -> None:
    await load(EN_AU, url=owner(tenant_db))
    async with tenant_db.with_tenant(TENANT_B_ID) as conn:
        result = await conn.execute(
            text("SELECT default_text FROM term_key WHERE key = 'inspection.status.completed'")
        )
        assert result.scalar_one() == "Completed"


async def test_mewp_and_ladder_are_separate_keys(tenant_db: TenantDb) -> None:
    await load(EN_AU, url=owner(tenant_db))
    async with tenant_db.with_tenant(TENANT_B_ID) as conn:
        rows = await conn.execute(
            text(
                "SELECT key, default_text FROM term_key WHERE key IN"
                " ('inspection.status.completed', 'access.method.mewp', 'access.method.ladder')"
                " ORDER BY key"
            )
        )
        assert rows.all() == [
            ("access.method.ladder", "Ladder"),
            ("access.method.mewp", "MEWP"),
            ("inspection.status.completed", "Completed"),
        ]


INSERT_PLATFORM_OVERRIDE = text(
    "INSERT INTO term_override (id, tenant_id, level, key, locale, text)"
    " VALUES (gen_random_uuid(), :tenant, 'tenant', 'inspection.status.completed', 'en-AU',"
    " 'Done')"
)


async def test_tenant_b_cannot_write_platform_rows(tenant_db: TenantDb) -> None:
    await load(EN_AU, url=owner(tenant_db))  # the override's key must exist (FK)
    with pytest.raises(DBAPIError) as caught:
        async with tenant_db.with_tenant(TENANT_B_ID) as conn:
            await conn.execute(INSERT_PLATFORM_OVERRIDE, {"tenant": PLATFORM_TENANT_ID})
    assert getattr(caught.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE


async def test_aip_app_cannot_write_platform_rows_even_bound_to_the_platform_tenant(
    tenant_db: TenantDb,
) -> None:
    await load(EN_AU, url=owner(tenant_db))
    with pytest.raises(DBAPIError) as caught:
        async with tenant_db.no_tenant() as conn:
            await conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"),
                {"t": str(PLATFORM_TENANT_ID)},
            )
            await conn.execute(INSERT_PLATFORM_OVERRIDE, {"tenant": PLATFORM_TENANT_ID})
    assert getattr(caught.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE term_key SET default_text = 'Hijacked' WHERE key = 'inspection.status.completed'",
        "DELETE FROM term_key",
        "INSERT INTO term_key (id, tenant_id, key, module_id, default_text)"
        " VALUES (gen_random_uuid(), :tenant, 'future.key.name', 'core', 'Squatted')",
    ],
)
async def test_a_tenant_cannot_change_the_key_catalogue(
    tenant_db: TenantDb, statement: str
) -> None:
    await load(EN_AU, url=owner(tenant_db))
    with pytest.raises(DBAPIError) as caught:
        async with tenant_db.with_tenant(TENANT_B_ID) as conn:
            await conn.execute(text(statement), {"tenant": TENANT_B_ID})
    assert getattr(caught.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE


async def test_tenant_overrides_are_isolated(tenant_db: TenantDb) -> None:
    await load(EN_AU, url=owner(tenant_db))
    async with tenant_db.with_tenant(TENANT_A_ID) as conn:
        await conn.execute(INSERT_PLATFORM_OVERRIDE, {"tenant": TENANT_A_ID})
    async with tenant_db.with_tenant(TENANT_A_ID) as conn:
        own = await conn.execute(text("SELECT text FROM term_override"))
        assert own.scalars().all() == ["Done"]
    async with tenant_db.with_tenant(TENANT_B_ID) as conn:
        other = await conn.execute(text("SELECT count(*) FROM term_override"))
        assert other.scalar_one() == 0


async def test_an_override_of_an_unknown_key_is_rejected(tenant_db: TenantDb) -> None:
    with pytest.raises(DBAPIError) as caught:
        async with tenant_db.with_tenant(TENANT_A_ID) as conn:
            await conn.execute(INSERT_PLATFORM_OVERRIDE, {"tenant": TENANT_A_ID})
    assert getattr(caught.value.orig, "sqlstate", None) == "23503"  # foreign_key_violation


async def test_with_platform_tenant_refuses_a_non_owner_login(tenant_db: TenantDb) -> None:
    with pytest.raises(PlatformTenantError, match="aip_owner"):
        async with with_platform_tenant(tenant_db.engine):
            pass


async def test_the_loader_refuses_a_non_owner_url(tenant_db: TenantDb) -> None:
    with pytest.raises(PlatformTenantError, match="aip_owner"):
        await load(EN_AU, url=tenant_db.db.app_url)
