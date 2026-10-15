"""TERMS-03: ICU message formatting, unit conversion and the Jinja template filters.

Unit tests run the shared golden vectors (``packages/contracts``) and a Hypothesis round trip.
Integration tests resolve through the TERMS-02 resolver and read ``locale_settings`` through
``aip_app`` (``tenant_db``, RLS on).
"""

from __future__ import annotations

import json
import math
import uuid
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import text
from structlog.testing import capture_logs
from tests.conftest import ALICE_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import REPO_ROOT, TenantDb

from aip.modules.terms import api
from aip.modules.terms.icu import MessageFormatError, render
from aip.modules.terms.loader import load
from aip.modules.terms.service import set_override
from aip.modules.terms.templating import (
    TemplateScope,
    render_template,
    template_environment,
    template_scope,
)
from aip.modules.terms.units import (
    UNITS,
    Quantity,
    UnknownUnitError,
    display_unit,
    round_trips,
    to_display,
    to_si,
)

EN_AU = REPO_ROOT / "config" / "terms" / "en-AU"
CONTRACTS = REPO_ROOT / "packages" / "contracts"
ICU_CASES: list[dict[str, Any]] = json.loads(
    (CONTRACTS / "icu-vectors" / "icu-v1.json").read_text(encoding="utf-8")
)["cases"]
UNIT_VECTORS: dict[str, Any] = json.loads(
    (CONTRACTS / "unit-vectors" / "units-v1.json").read_text(encoding="utf-8")
)
COMPLETED = "inspection.status.completed"
KIND = "inspection.kind.inspection"  # any catalogue key: overrides reference term_key
IMPERIAL_PROJECT = UUID("00000000-0000-4000-8000-0000000003a1")
METRIC_PROJECT = UUID("00000000-0000-4000-8000-0000000003a2")
DEFECTS = "{n, plural, one {# defect} other {# defects}}"


# --- unit: ICU ---------------------------------------------------------------------------------


@pytest.mark.parametrize("case", ICU_CASES, ids=[c["name"] for c in ICU_CASES])
def test_icu_golden_vectors(case: dict[str, Any]) -> None:
    assert render(case["message"], case["args"], case["locale"]) == case["expected"]


def test_plural_defects() -> None:
    assert render(DEFECTS, {"n": 1}, "en-AU") == "1 defect"
    assert render(DEFECTS, {"n": 3}, "en-AU") == "3 defects"


@pytest.mark.parametrize(
    ("message", "args"),
    [
        (DEFECTS, {}),  # missing argument
        (DEFECTS, {"n": "three"}),  # plural needs a number
        ("{n, plural, one {# a} other {# b}", {"n": 1}),  # unbalanced braces
        ("{when, date, short}", {"when": 1}),  # unsupported type
    ],
)
def test_a_bad_message_or_argument_raises(message: str, args: dict[str, Any]) -> None:
    with pytest.raises(MessageFormatError):
        render(message, args, "en-AU")


def test_decimal_arguments_format_like_floats() -> None:
    # asyncpg returns numeric columns as Decimal.
    assert render("{x, number, integer}", {"x": Decimal("3.5")}, "en-AU") == "4"
    assert render(DEFECTS, {"n": Decimal("2")}, "en-AU") == "2 defects"
    assert render("{x, number}", {"x": Decimal("1234.5")}, "en-AU") == "1,234.5"


def test_none_prints_as_empty_like_intl() -> None:
    assert render("[{x}]", {"x": None}, "en-AU") == "[]"


def test_an_unknown_locale_formats_as_en_au() -> None:
    assert render("{x, number}", {"x": 1234.5}, "xx-ZZ") == "1,234.5"


# --- unit: units -------------------------------------------------------------------------------


def test_one_inch_displays_as_1_00_in() -> None:
    q = to_display(25.4, "mm", "imperial")
    assert (q.value, q.unit) == (1.0, "in")
    assert q.format() == "1.00 in"


def test_boiling_point_and_ten_bar() -> None:
    assert to_display(100, "degC", "imperial") == Quantity(212.0, "degF", 1)
    psi = to_display(10, "bar", "imperial")
    assert psi.unit == "psi"
    assert psi.format() == "145.04 psi"


def test_conversion_does_not_round() -> None:
    assert to_display(1000, "mm", "imperial").value == pytest.approx(39.37007874015748, rel=1e-15)


def test_unit_table_matches_the_contract() -> None:
    for code, spec in UNIT_VECTORS["units"].items():
        unit = UNITS[code]
        assert (unit.symbol, unit.si, unit.decimals) == (
            spec["symbol"],
            spec["si"],
            spec["decimals"],
        )
    for system, mapping in UNIT_VECTORS["systems"].items():
        for si, shown in mapping.items():
            assert display_unit(si, system) == shown
    assert set(UNITS) == set(UNIT_VECTORS["units"])


@pytest.mark.parametrize(
    "case", UNIT_VECTORS["to_display"], ids=[c["name"] for c in UNIT_VECTORS["to_display"]]
)
def test_to_display_golden_vectors(case: dict[str, Any]) -> None:
    q = to_display(case["value"], case["unit"], case["system"])
    want = case["expected"]
    assert q.unit == want["unit"]
    assert round_trips(want["value"], q.value)
    assert q.format("en-AU") == want["text"]


@pytest.mark.parametrize(
    "case", UNIT_VECTORS["to_si"], ids=[c["name"] for c in UNIT_VECTORS["to_si"]]
)
def test_to_si_golden_vectors(case: dict[str, Any]) -> None:
    assert round_trips(case["expected"], to_si(case["value"], case["unit"]))


def test_unknown_units_are_refused() -> None:
    with pytest.raises(UnknownUnitError):
        to_si(1, "furlong")
    with pytest.raises(UnknownUnitError):
        to_display(1, "in", "imperial")  # "in" is not an SI storage unit


@given(
    x=st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
    si_unit=st.sampled_from(["mm", "bar", "degC"]),
    system=st.sampled_from(["metric", "imperial"]),
)
def test_round_trip_stays_within_tolerance(x: float, si_unit: str, system: Any) -> None:
    shown = to_display(x, si_unit, system)
    back = to_si(shown.value, shown.unit)
    assert math.isfinite(back)
    assert round_trips(x, back), (x, shown, back)


# --- integration -------------------------------------------------------------------------------


@pytest.fixture
async def terms_db(tenant_db: TenantDb) -> TenantDb:
    await load(EN_AU, url=tenant_db.db.owner_url)
    return tenant_db


async def set_unit_system(db: TenantDb, tenant: UUID, system: str, project: UUID | None) -> None:
    async with db.with_tenant(tenant) as conn:
        await conn.execute(
            text(
                "INSERT INTO locale_settings (id, tenant_id, project_id, unit_system)"
                " VALUES (:id, :tenant, :project, :system)"
            ),
            {"id": uuid.uuid4(), "tenant": tenant, "project": project, "system": system},
        )


async def test_fmt_measure_follows_the_project_unit_system(terms_db: TenantDb) -> None:
    await set_unit_system(terms_db, TENANT_A_ID, "metric", None)
    await set_unit_system(terms_db, TENANT_A_ID, "imperial", IMPERIAL_PROJECT)
    env = template_environment()
    template = env.from_string("{{ thickness | fmt_measure('mm') }}")
    stored = 6.35
    out = {}
    async with terms_db.with_tenant(TENANT_A_ID) as conn:
        for project in (IMPERIAL_PROJECT, METRIC_PROJECT):
            scope = await template_scope(conn, TENANT_A_ID, "en-AU", project_id=project)
            out[project] = await render_template(template, scope, thickness=stored)
    assert out == {IMPERIAL_PROJECT: "0.25 in", METRIC_PROJECT: "6.35 mm"}
    assert stored == 6.35


async def test_display_system_falls_back_project_tenant_metric(terms_db: TenantDb) -> None:
    async with terms_db.with_tenant(TENANT_B_ID) as conn:
        assert await api.display_system(conn, TENANT_B_ID) == "metric"  # no rows at all
    await set_unit_system(terms_db, TENANT_B_ID, "imperial", None)
    await set_unit_system(terms_db, TENANT_B_ID, "metric", METRIC_PROJECT)
    async with terms_db.with_tenant(TENANT_B_ID) as conn:
        assert await api.display_system(conn, TENANT_B_ID) == "imperial"
        assert await api.display_system(conn, TENANT_B_ID, IMPERIAL_PROJECT) == "imperial"
        assert await api.display_system(conn, TENANT_B_ID, METRIC_PROJECT) == "metric"
    async with terms_db.with_tenant(TENANT_A_ID) as conn:  # B's settings never reach A
        assert await api.display_system(conn, TENANT_A_ID) == "metric"


async def test_format_message_uses_a_tenant_override_when_one_exists(terms_db: TenantDb) -> None:
    async with terms_db.with_tenant(TENANT_A_ID) as conn:
        assert await api.format_message(conn, COMPLETED, {}, "en-AU", tenant_id=TENANT_A_ID) == (
            "Completed"
        )
        await set_override(
            conn,
            tenant_id=TENANT_A_ID,
            key=COMPLETED,
            locale="en-AU",
            text="Closed out",
            actor_id=ALICE_ID,
        )
    async with terms_db.with_tenant(TENANT_A_ID) as conn:
        assert await api.format_message(conn, COMPLETED, {}, "en-AU", tenant_id=TENANT_A_ID) == (
            "Closed out"
        )
    async with terms_db.with_tenant(TENANT_B_ID) as conn:
        assert await api.format_message(conn, COMPLETED, {}, "en-AU", tenant_id=TENANT_B_ID) == (
            "Completed"
        )


async def test_an_override_with_plural_syntax_formats_its_arguments(terms_db: TenantDb) -> None:
    async with terms_db.with_tenant(TENANT_A_ID) as conn:
        await set_override(conn, tenant_id=TENANT_A_ID, key=KIND, locale="en-AU", text=DEFECTS)
    env = template_environment()
    template = env.from_string("{{ '" + KIND + "' | t(n=n) }} / {{ '" + COMPLETED + "' | t }}")
    async with terms_db.with_tenant(TENANT_A_ID) as conn:
        scope = await template_scope(conn, TENANT_A_ID, "en-AU")
        assert await render_template(template, scope, n=3) == "3 defects / Completed"


async def test_a_broken_override_shows_the_visible_fallback(terms_db: TenantDb) -> None:
    async with terms_db.with_tenant(TENANT_A_ID) as conn:
        await set_override(
            conn, tenant_id=TENANT_A_ID, key=COMPLETED, locale="en-AU", text="{n, plural, one {x}"
        )
    with capture_logs() as logs:
        async with terms_db.with_tenant(TENANT_A_ID) as conn:
            out = await api.format_message(conn, COMPLETED, {}, "en-AU", tenant_id=TENANT_A_ID)
    assert out == f"⟦{COMPLETED}⟧"
    assert any(log["event"] == "terms.format_error" for log in logs)


async def test_t_output_is_html_escaped(terms_db: TenantDb) -> None:
    async with terms_db.with_tenant(TENANT_A_ID) as conn:
        await set_override(
            conn, tenant_id=TENANT_A_ID, key=COMPLETED, locale="en-AU", text="<b>Done</b>"
        )
    template = template_environment().from_string("{{ '" + COMPLETED + "' | t }}")
    async with terms_db.with_tenant(TENANT_A_ID) as conn:
        scope = TemplateScope(conn, TENANT_A_ID, "en-AU", "metric")
        assert await render_template(template, scope) == "&lt;b&gt;Done&lt;/b&gt;"


async def test_t_accepts_an_icu_argument_named_key(terms_db: TenantDb) -> None:
    async with terms_db.with_tenant(TENANT_A_ID) as conn:
        await set_override(conn, tenant_id=TENANT_A_ID, key=KIND, locale="en-AU", text="K={key}")
    template = template_environment().from_string("{{ '" + KIND + "' | t(key='v') }}")
    async with terms_db.with_tenant(TENANT_A_ID) as conn:
        scope = TemplateScope(conn, TENANT_A_ID, "en-AU", "metric")
        assert await render_template(template, scope) == "K=v"


async def test_rendering_without_a_scope_is_refused() -> None:
    template = template_environment().from_string("{{ 1 | fmt_measure('mm') }}")
    with pytest.raises(RuntimeError, match="TemplateScope"):
        await template.render_async()
