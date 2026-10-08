"""baseline_extensions

The greenfield baseline (ADR 0001: nothing is derived from any AIP schema or Alembic history).
Installs the trusted extensions; `vector` is created by db/bootstrap/00_cluster.sql because
pgvector is not a trusted extension. No PostGIS until a module needs it (ADR 0002).

Revision ID: 202610071200
Revises:
Create Date: 2026-10-07 12:00:00+00:00
"""

from alembic import op

revision: str = "202610071200"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE EXTENSION IF NOT EXISTS ltree;
    CREATE EXTENSION IF NOT EXISTS pgcrypto;
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    CREATE EXTENSION IF NOT EXISTS citext;
    CREATE EXTENSION IF NOT EXISTS btree_gist;
    """)
    op.execute("""
    DO $$
    DECLARE
      ext text;
    BEGIN
      FOREACH ext IN ARRAY ARRAY['ltree', 'pgcrypto', 'pg_trgm', 'citext', 'btree_gist', 'vector']
      LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = ext) THEN
          RAISE EXCEPTION 'missing extension %', ext;
        END IF;
      END LOOP;
    END
    $$;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
