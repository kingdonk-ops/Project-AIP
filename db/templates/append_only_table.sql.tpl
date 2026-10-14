-- DATABASE-05 / ADR 0002: an append-only evidence table, range-partitioned by month. Render it with
--   op.execute(render_template("append_only_table", table="audit_log",
--                              columns="action text NOT NULL", partition_column="created_at"))
-- `table` is an unqualified snake_case name; `columns` is the comma-separated list of the
-- table's own columns; `partition_column` is a timestamptz column (`created_at`, or one of
-- `columns`). Rows are never changed or removed, so there is no `updated_at` or `deleted_at`.
--
-- Register the table in `partition_settings` in the same revision: the `ensure_partitions` job
-- (aip.platform.db.jobs) then keeps monthly partitions `<table>_YYYY_MM` created ahead of time.
-- Until a month's partition exists its rows land in `<table>_default`; the job moves them.
--
-- RLS fails closed exactly as in tenant_table.sql.tpl. Partitions get no grants and are reached
-- only through this table, so its policy covers them (the schema guard checks the parent).
CREATE TABLE {{table}} (
  id uuid NOT NULL,
  tenant_id uuid NOT NULL,
  {{columns}},
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_{{table}} PRIMARY KEY (id, {{partition_column}})
) PARTITION BY RANGE ({{partition_column}});

CREATE TABLE {{table}}_default PARTITION OF {{table}} DEFAULT;

CREATE INDEX ix_{{table}}_tenant_id ON {{table}} (tenant_id);

ALTER TABLE {{table}} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {{table}} FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON {{table}}
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Explicit, so a default privilege or an earlier grant cannot leave a way to change evidence.
REVOKE UPDATE, DELETE, TRUNCATE ON {{table}} FROM aip_app, aip_jobs, aip_readonly;
GRANT SELECT, INSERT ON {{table}} TO aip_app;
GRANT SELECT ON {{table}} TO aip_readonly;
