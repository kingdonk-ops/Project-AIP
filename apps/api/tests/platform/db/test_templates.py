"""DATABASE-02: ``render_template`` and ``db/templates/tenant_table.sql.tpl``."""

from __future__ import annotations

import pytest

from aip.platform.db.errors import TemplateError
from aip.platform.db.migrator.lint import sql_statements
from aip.platform.db.templates import render_template


def test_tenant_table_has_forced_fail_closed_rls_and_grants() -> None:
    sql = render_template("tenant_table", table="x", columns="name text")
    assert "CREATE TABLE x (" in sql
    assert "name text," in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "NULLIF(current_setting('app.tenant_id', true), '')::uuid" in sql
    assert "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)" in sql
    assert (
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)" in sql
    )
    assert "CREATE INDEX ix_x_tenant_id ON x (tenant_id)" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON x TO aip_app" in sql
    assert "GRANT SELECT ON x TO aip_readonly" in sql
    assert "{{" not in sql


def test_tenant_table_has_the_standard_columns() -> None:
    statements = sql_statements(render_template("tenant_table", table="x", columns="n int"))
    create = next(s for s in statements if s.startswith("CREATE TABLE"))
    for column in (
        "ID UUID NOT NULL",
        "TENANT_ID UUID NOT NULL",
        "CREATED_AT TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        "UPDATED_AT TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        "DELETED_AT TIMESTAMPTZ NULL",
        "CONSTRAINT PK_X PRIMARY KEY (ID)",
    ):
        assert column in create


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"table": "X", "columns": "a int"}, "snake_case identifier"),
        ({"table": "x; DROP TABLE y", "columns": "a int"}, "snake_case identifier"),
        ({"table": "public.x", "columns": "a int"}, "snake_case identifier"),
        ({"table": "x", "columns": ""}, "must not be empty"),
        ({"table": "x", "columns": "a int); DROP TABLE y; --"}, "must not contain"),
        ({"table": "x"}, "needs columns"),
        ({"table": "x", "columns": "a int", "extra": "1"}, "no placeholder for extra"),
        ({"table": "x", "columns": 3}, "must be a string"),
    ],
)
def test_bad_variables_are_rejected(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(TemplateError, match=message):
        render_template("tenant_table", **kwargs)


def test_unknown_or_unsafe_template_names_are_rejected() -> None:
    with pytest.raises(TemplateError, match="unknown template"):
        render_template("nope")
    with pytest.raises(TemplateError, match="invalid template name"):
        render_template("../bootstrap/00_cluster")
