"""partition_fk_attach

DATABASE-09: ``aip_ensure_partitions`` works for append-only tables that have a foreign key.

DATABASE-05 moved a month's rows out of ``<table>_default`` into the new ``<table>_YYYY_MM`` and
then attached it. ``ATTACH PARTITION`` validates each foreign key cloned onto the partition in one
bulk query, run as ``aip_owner`` with no ``app.tenant_id``; FORCE RLS on the referenced table hides
every parent row, so the attach raised a foreign-key violation (``workflow_definition_audit``,
``fk_workflow_definition_audit_definition``).

Now the rows go to a temporary staging table, the still-empty partition is attached (nothing to
validate), and the rows are inserted into the attached partition. Each insert is checked by the
per-row foreign-key trigger, which Postgres runs as the referenced table's owner with FORCE RLS
lifted for that lookup only, exactly as for an ordinary insert by ``aip_app``. No role gains
BYPASSRLS and no table's FORCE RLS is switched off. Row triggers a parent defines for INSERT fire
for the moved rows; no append-only table has one.

Also hardened: ``pg_temp`` is now last in the function's ``search_path`` and catalog names are
schema-qualified, so a temporary table the caller made cannot stand in for a catalog.

Revision ID: 202611011400
Revises: 202611011300
Create Date: 2026-11-01 14:00:00+00:00
"""

from alembic import op

revision: str = "202611011400"
down_revision: str | None = "202611011300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # contract: 202611011400 SECURITY DEFINER on purpose, as in 202610141100: partitions must
    # belong to the table owner, and aip_jobs has no CREATE. Owned by aip_owner, search_path fixed
    # with pg_temp last, accepts only a partitioned table listed in partition_settings, bounded
    # months_ahead, identifiers through format(%I) and bounds through %L; EXECUTE for aip_jobs
    # only. Rows are staged in a temporary table of the owner's and re-inserted after the attach,
    # so foreign keys are checked per row by Postgres' own trigger (FORCE RLS stays on).
    op.execute("""
    CREATE OR REPLACE FUNCTION aip_ensure_partitions(p_table text, p_months_ahead integer)
    RETURNS SETOF text
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = pg_catalog, public, pg_temp
    AS $fn$
    DECLARE
      v_parent regclass;
      v_column text;
      v_default text;
      v_month timestamp := date_trunc('month', now() AT TIME ZONE 'UTC');
      v_from timestamptz;
      v_to timestamptz;
      v_name text;
      v_moved bigint;
    BEGIN
      IF p_months_ahead IS NULL OR p_months_ahead NOT BETWEEN 0 AND 24 THEN
        RAISE EXCEPTION 'aip_ensure_partitions: months_ahead must be 0 to 24, got %', p_months_ahead
          USING ERRCODE = '22023';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM public.partition_settings AS s WHERE s.table_name = p_table) THEN
        RAISE EXCEPTION 'aip_ensure_partitions: % is not listed in partition_settings', p_table
          USING ERRCODE = '22023';
      END IF;
      SELECT pt.partrelid, a.attname, d.relname INTO v_parent, v_column, v_default
      FROM pg_catalog.pg_partitioned_table AS pt
      JOIN pg_catalog.pg_class AS c ON c.oid = pt.partrelid
      JOIN pg_catalog.pg_attribute AS a
        ON a.attrelid = pt.partrelid AND a.attnum = pt.partattrs[0]
      LEFT JOIN pg_catalog.pg_class AS d ON d.oid = pt.partdefid
      WHERE c.relnamespace = 'public'::regnamespace AND c.relname = p_table
        AND pt.partstrat = 'r' AND pt.partnatts = 1 AND a.atttypid = 'timestamptz'::regtype;
      IF v_parent IS NULL THEN
        RAISE EXCEPTION 'aip_ensure_partitions: % is not range-partitioned on a timestamptz column',
          p_table USING ERRCODE = '22023';
      END IF;

      FOR i IN 0..p_months_ahead LOOP
        v_from := (v_month + make_interval(months => i)) AT TIME ZONE 'UTC';
        v_to := (v_month + make_interval(months => i + 1)) AT TIME ZONE 'UTC';
        v_name := p_table || '_' || to_char(v_month + make_interval(months => i), 'YYYY_MM');
        CONTINUE WHEN to_regclass(format('public.%I', v_name)) IS NOT NULL;

        EXECUTE format('CREATE TABLE public.%I '
                       '(LIKE public.%I INCLUDING DEFAULTS INCLUDING CONSTRAINTS)',
                       v_name, p_table);
        v_moved := 0;
        IF v_default IS NOT NULL THEN
          -- Attaching scans the default partition anyway; lock it first so no row for this month
          -- can arrive between the move and the attach.
          EXECUTE format('LOCK TABLE public.%I IN ACCESS EXCLUSIVE MODE', v_default);
          -- Staged, not moved straight into the partition: attaching a partition with rows would
          -- validate its foreign keys in one query that FORCE RLS on the parent table blinds.
          DROP TABLE IF EXISTS pg_temp.aip_partition_stage;
          EXECUTE format('CREATE TEMPORARY TABLE aip_partition_stage (LIKE public.%I) '
                         'ON COMMIT DROP', p_table);
          EXECUTE format('WITH moved AS (DELETE FROM public.%I '
                         'WHERE %I >= $1 AND %I < $2 RETURNING *) '
                         'INSERT INTO pg_temp.aip_partition_stage SELECT * FROM moved',
                         v_default, v_column, v_column)
            USING v_from, v_to;
          GET DIAGNOSTICS v_moved = ROW_COUNT;
        END IF;
        EXECUTE format('ALTER TABLE public.%I ATTACH PARTITION public.%I '
                       'FOR VALUES FROM (%L) TO (%L)',
                       p_table, v_name, v_from, v_to);
        IF v_default IS NOT NULL THEN
          IF v_moved > 0 THEN
            EXECUTE format('INSERT INTO public.%I SELECT * FROM pg_temp.aip_partition_stage',
                           v_name);
          END IF;
          DROP TABLE pg_temp.aip_partition_stage;
        END IF;
        RETURN NEXT v_name;
      END LOOP;
    END
    $fn$;
    REVOKE ALL ON FUNCTION aip_ensure_partitions(text, integer) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION aip_ensure_partitions(text, integer) TO aip_jobs;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
