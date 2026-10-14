"""append_only_grants

DATABASE-05 (ADR 0002): evidence tables are append-only for the application roles.

None of the evidence tables exists on main yet, so there is nothing to revoke here. Each of these
must use ``db/templates/append_only_table.sql.tpl`` when its module creates it (the template
grants ``aip_app`` only SELECT and INSERT, revokes UPDATE, DELETE and TRUNCATE from ``aip_app``,
``aip_jobs`` and ``aip_readonly``, and partitions the table by month):

- ``inspection_responses`` (inspections)
- ``audit_log`` (audit; AUDIT-01)
- ``sync_operations`` (sync)
- ``activity`` (activity feed)

``aip_convert_to_partitioned(table)`` is the expand/contract path for a plain table that already
holds rows. In one revision, as ``aip_owner``::

    op.execute(render_template("append_only_table", table="<table>_p", columns=...,
                               partition_column="created_at"))
    # contract: <this revision> converts <table> (copy, verify, drop the old table)
    op.execute("SELECT aip_convert_to_partitioned('<table>')")
    op.execute("INSERT INTO partition_settings (table_name) VALUES ('<table>')")

The function copies every row into ``<table>_p``, compares row count and an md5 checksum of the
rows in ``id`` order, and only when both match drops the old table and renames ``<table>_p``
(and its ``pk_``/``ix_`` indexes and partitions) to the old names. A mismatch raises, so the
whole revision rolls back with the old table intact. The old table's own extra columns (for
example ``updated_at``) are not copied: the checksum covers the columns the new table keeps.

Revision ID: 202610141000
Revises: 202610131600
Create Date: 2026-10-14 10:00:00+00:00
"""

from alembic import op

revision: str = "202610141000"
down_revision: str | None = "202610131600"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # contract: 202610141000 expand/contract for append-only tables: the DROP TABLE runs only
    # after the count and checksum match. FORCE RLS binds the owner too, so the copy lifts it on
    # both tables inside the revision's transaction and restores it on the new table; any error
    # rolls all of it back. Not SECURITY DEFINER; EXECUTE is revoked from PUBLIC, so only the
    # owner (the migrator) can run it.
    op.execute("""
    CREATE FUNCTION aip_convert_to_partitioned(p_table text)
    RETURNS bigint
    LANGUAGE plpgsql
    SET search_path = pg_catalog, public
    AS $fn$
    DECLARE
      v_new text := p_table || '_p';
      v_old regclass := to_regclass(format('public.%I', p_table));
      v_target regclass := to_regclass(format('public.%I', v_new));
      v_cols text;
      v_old_count bigint;
      v_new_count bigint;
      v_old_sum text;
      v_new_sum text;
      v_name text;
    BEGIN
      IF v_old IS NULL OR (SELECT relkind FROM pg_class WHERE oid = v_old) <> 'r' THEN
        RAISE EXCEPTION 'aip_convert_to_partitioned: % is not a plain table', p_table
          USING ERRCODE = '42809';
      END IF;
      IF v_target IS NULL OR (SELECT relkind FROM pg_class WHERE oid = v_target) <> 'p' THEN
        RAISE EXCEPTION 'aip_convert_to_partitioned: render % from append_only_table.sql.tpl first',
          v_new USING ERRCODE = '42809';
      END IF;
      EXECUTE format('LOCK TABLE public.%I IN ACCESS EXCLUSIVE MODE', p_table);

      SELECT string_agg(format('%I', a.attname), ', ' ORDER BY a.attnum) INTO v_cols
      FROM pg_attribute AS a
      WHERE a.attrelid = v_target AND a.attnum > 0 AND NOT a.attisdropped;

      EXECUTE format('ALTER TABLE public.%I NO FORCE ROW LEVEL SECURITY', p_table);
      EXECUTE format('ALTER TABLE public.%I NO FORCE ROW LEVEL SECURITY', v_new);
      EXECUTE format('INSERT INTO public.%I (%s) SELECT %s FROM public.%I',
                     v_new, v_cols, v_cols, p_table);
      EXECUTE format('SELECT count(*), md5(string_agg(ROW(%s)::text, '','' ORDER BY id)) '
                     'FROM public.%I', v_cols, p_table)
        INTO v_old_count, v_old_sum;
      EXECUTE format('SELECT count(*), md5(string_agg(ROW(%s)::text, '','' ORDER BY id)) '
                     'FROM public.%I', v_cols, v_new)
        INTO v_new_count, v_new_sum;
      IF v_old_count <> v_new_count OR v_old_sum IS DISTINCT FROM v_new_sum THEN
        RAISE EXCEPTION
          'aip_convert_to_partitioned: % copy differs (count % -> %, checksum % -> %)',
          p_table, v_old_count, v_new_count, v_old_sum, v_new_sum;
      END IF;

      EXECUTE format('DROP TABLE public.%I', p_table);
      EXECUTE format('ALTER TABLE public.%I RENAME TO %I', v_new, p_table);
      EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', p_table);
      -- The template names follow the table: pk_/ix_<table>_p..., <table>_p_default, ...
      FOR v_name IN
        SELECT c.relname FROM pg_index AS i JOIN pg_class AS c ON c.oid = i.indexrelid
        WHERE i.indrelid = v_target AND strpos(c.relname, v_new) > 0
      LOOP
        EXECUTE format('ALTER INDEX public.%I RENAME TO %I',
                       v_name, replace(v_name, v_new, p_table));
      END LOOP;
      FOR v_name IN
        SELECT c.relname FROM pg_inherits AS h JOIN pg_class AS c ON c.oid = h.inhrelid
        WHERE h.inhparent = v_target AND left(c.relname, length(v_new) + 1) = v_new || '_'
      LOOP
        EXECUTE format('ALTER TABLE public.%I RENAME TO %I',
                       v_name, p_table || substr(v_name, length(v_new) + 1));
      END LOOP;
      RETURN v_new_count;
    END
    $fn$;
    REVOKE ALL ON FUNCTION aip_convert_to_partitioned(text) FROM PUBLIC;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
