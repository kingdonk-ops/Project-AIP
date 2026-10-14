"""partition_functions

DATABASE-05 (ADR 0002, ADR 0003): monthly partitions for append-only tables, created ahead.

- ``partition_settings``: one row per partitioned append-only table (``table_name``), with
  ``partition_interval`` (``month`` only for now) and ``months_ahead`` (default 3). Global
  reference data, allow-listed in the schema guard (TESTING-02). ``aip_jobs`` may only read it.
- ``aip_ensure_partitions(table_name, months_ahead)``: creates the missing partitions
  ``<table>_YYYY_MM`` for this UTC month and the next ``months_ahead`` months and returns their
  names. Rows that landed in ``<table>_default`` for such a month are moved into the new
  partition before it is attached. Only tables listed in ``partition_settings`` are accepted.
  ``SECURITY DEFINER`` owned by ``aip_owner`` (the partitions belong to the table owner), with
  ``EXECUTE`` for ``aip_jobs`` only: the ``ensure_partitions`` job (``aip.platform.db.jobs``)
  calls it daily.

Partitions get no grants and no policy of their own: they are reached only through the parent,
whose FORCE RLS policy applies (the schema guard checks partitions through their parent). That is
also why the owner can move rows out of the default partition by addressing it directly.

Revision ID: 202610141100
Revises: 202610141000
Create Date: 2026-10-14 11:00:00+00:00
"""

from alembic import op

revision: str = "202610141100"
down_revision: str | None = "202610141000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE partition_settings (
      table_name text NOT NULL,
      partition_interval text NOT NULL DEFAULT 'month',
      months_ahead integer NOT NULL DEFAULT 3,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT pk_partition_settings PRIMARY KEY (table_name),
      CONSTRAINT ck_partition_settings_interval CHECK (partition_interval = 'month'),
      CONSTRAINT ck_partition_settings_months_ahead CHECK (months_ahead BETWEEN 0 AND 24)
    );
    REVOKE ALL ON TABLE partition_settings FROM PUBLIC;
    GRANT SELECT ON partition_settings TO aip_jobs;
    """)
    # contract: 202610141100 SECURITY DEFINER on purpose: partitions must belong to the table
    # owner, and aip_jobs has no CREATE. Owned by aip_owner, fixed search_path, accepts only a
    # partitioned table listed in partition_settings, bounded months_ahead, identifiers through
    # format(%I) and bounds through %L; EXECUTE for aip_jobs only.
    op.execute("""
    CREATE FUNCTION aip_ensure_partitions(p_table text, p_months_ahead integer)
    RETURNS SETOF text
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $fn$
    DECLARE
      v_parent regclass;
      v_column text;
      v_default text;
      v_month timestamp := date_trunc('month', now() AT TIME ZONE 'UTC');
      v_from timestamptz;
      v_to timestamptz;
      v_name text;
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
      FROM pg_partitioned_table AS pt
      JOIN pg_class AS c ON c.oid = pt.partrelid
      JOIN pg_attribute AS a ON a.attrelid = pt.partrelid AND a.attnum = pt.partattrs[0]
      LEFT JOIN pg_class AS d ON d.oid = pt.partdefid
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
        IF v_default IS NOT NULL THEN
          -- Attaching scans the default partition anyway; lock it first so no row for this month
          -- can arrive between the move and the attach.
          EXECUTE format('LOCK TABLE public.%I IN ACCESS EXCLUSIVE MODE', v_default);
          EXECUTE format('WITH moved AS (DELETE FROM public.%I '
                         'WHERE %I >= $1 AND %I < $2 RETURNING *) '
                         'INSERT INTO public.%I SELECT * FROM moved',
                         v_default, v_column, v_column, v_name)
            USING v_from, v_to;
        END IF;
        EXECUTE format('ALTER TABLE public.%I ATTACH PARTITION public.%I '
                       'FOR VALUES FROM (%L) TO (%L)',
                       p_table, v_name, v_from, v_to);
        RETURN NEXT v_name;
      END LOOP;
    END
    $fn$;
    REVOKE ALL ON FUNCTION aip_ensure_partitions(text, integer) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION aip_ensure_partitions(text, integer) TO aip_jobs;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
