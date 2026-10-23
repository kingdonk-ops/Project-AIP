-- ACCESS-03 / ADR 0002: the project-scope RLS for a tenant table that carries a project_id record
-- column. Render it AFTER the table's own render_template("tenant_table", ...), with
--   op.execute(render_template("project_scoped_policy", table="inspections"))
-- `table` is the unqualified snake_case name; the table must already have a `project_id uuid`
-- column (NULL or NOT NULL) and the standard tenant-isolation policy.
--
-- It adds a RESTRICTIVE policy (so it ANDs with tenant isolation) that defers to
-- access_project_visible(project_id): a system/api_client principal and a tenant-scoped user see
-- every row, a project-scoped user only rows on a project they hold, and with no principal set the
-- table returns no rows and refuses writes (fail closed). The matching index keeps the predicate
-- cheap. Every later table with a project_id copies this; the project-scope coverage test
-- (tests/access/test_project_scope_coverage.py) fails CI for a project_id table that does not.
CREATE POLICY project_scope ON {{table}}
  AS RESTRICTIVE
  FOR ALL
  TO aip_app
  USING (access_project_visible(project_id))
  WITH CHECK (access_project_visible(project_id));

CREATE INDEX ix_{{table}}_tenant_id_project_id ON {{table}} (tenant_id, project_id);
