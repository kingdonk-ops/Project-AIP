-- DATABASE-02 / ADR 0002: a tenant-scoped table. Render it with
--   op.execute(render_template("tenant_table", table="widgets", columns="name text NOT NULL"))
-- `table` is an unqualified snake_case name; `columns` is the comma-separated list of the
-- table's own columns (the standard ones below are added for you).
--
-- RLS fails closed: with app.tenant_id unset or '' the NULLIF yields NULL, so no row matches
-- USING (reads see 0 rows) and every write fails WITH CHECK (SQLSTATE 42501).
-- FORCE applies the policy to the owner too; only a superuser or BYPASSRLS role skips it.
CREATE TABLE {{table}} (
  id uuid NOT NULL,
  tenant_id uuid NOT NULL,
  {{columns}},
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL,
  CONSTRAINT pk_{{table}} PRIMARY KEY (id)
);

CREATE INDEX ix_{{table}}_tenant_id ON {{table}} (tenant_id);

ALTER TABLE {{table}} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {{table}} FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON {{table}}
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

GRANT SELECT, INSERT, UPDATE, DELETE ON {{table}} TO aip_app;
GRANT SELECT ON {{table}} TO aip_readonly;
