"""DATABASE-07 unit tests: the isolation generator's cases, overrides and seed values (no DB)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, Text, Uuid

from .generator import (
    OVERRIDES_PATH,
    Case,
    OverrideError,
    cases,
    check_literals,
    literal_for,
    load_overrides,
    parse_overrides,
)


def _fixture_metadata() -> MetaData:
    meta = MetaData()
    Table("widgets", meta, Column("id", Uuid, primary_key=True), Column("tenant_id", Uuid))
    Table(
        "chain_heads",
        meta,
        Column("tenant_id", Uuid, primary_key=True),
        Column("stream", Text, primary_key=True),
    )
    Table("tenants", meta, Column("id", Uuid, primary_key=True), Column("name", Text))
    Table("regions", meta, Column("code", Text, primary_key=True), Column("n", Integer))
    return meta


def test_one_case_per_tenant_table() -> None:
    assert cases(_fixture_metadata()) == [
        Case("chain_heads", "tenant_id", ("tenant_id", "stream")),
        Case("tenants", "id", ("id",)),
        Case("widgets", "tenant_id", ("id",)),
    ]


def test_overrides_need_a_reason_and_known_keys() -> None:
    with pytest.raises(OverrideError, match="widgets: needs a reason"):
        parse_overrides({"tables": {"widgets": {"values": {"kind": "'a'"}}}})
    with pytest.raises(OverrideError, match="widgets: unknown keys"):
        parse_overrides({"tables": {"widgets": {"reason": "x", "colour": "red"}}})
    parsed = parse_overrides(
        {"tables": {"widgets": {"reason": "kind CHECK", "values": {"kind": "'a'"}}}}
    )
    assert (parsed["widgets"].values, parsed["widgets"].skip) == ({"kind": "'a'"}, False)


def test_the_committed_overrides_file_is_valid() -> None:
    assert Path(__file__).with_name("overrides.toml") == OVERRIDES_PATH
    for override in load_overrides().values():
        assert override.reason.strip()


@pytest.mark.parametrize(
    ("type_name", "expected"),
    [
        ("uuid", None),  # uuids are generated per row, not from a fixed literal
        ("text", "'iso_name_a'"),
        ("citext", "'iso_name_a'"),
        ("character varying(200)", "'iso_name_a'"),
        ("integer", "1"),
        ("bigint", "1"),
        ("numeric(9,6)", "1"),
        ("boolean", "false"),
        ("timestamp with time zone", "now()"),
        ("date", "current_date"),
        ("jsonb", "'{}'::jsonb"),
        ("inet", "'192.0.2.1'::inet"),
        ("bytea", "decode(repeat('aa', 32), 'hex')"),
        ("ltree", "'iso'::ltree"),
        ("text[]", "'{}'::text[]"),
        ("character(3)", "'AAA'"),
        ("tsvector", "?"),
    ],
)
def test_literal_for_each_column_type(type_name: str, expected: str | None) -> None:
    got = literal_for(type_name, "name", "a")
    if expected == "?":
        assert got is None or got == "?"  # unknown types are left for an override
    else:
        assert got == expected


def test_single_column_in_lists_and_equalities_become_seed_values() -> None:
    defs = [
        "CHECK ((status = ANY (ARRAY['draft'::text, 'active'::text])))",
        "CHECK ((stream = 'audit'::text))",
        "CHECK ((code <> ''::text))",
        "CHECK (((lat >= ('-90'::integer)::numeric) AND (lat <= (90)::numeric)))",
    ]
    assert check_literals(defs) == {"status": "'draft'", "stream": "'audit'"}
