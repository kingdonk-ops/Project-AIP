"""The single SQLAlchemy ``MetaData`` that platform and module ``tables.py`` attach to (ADR 0002).

Tables are declared with SQLAlchemy Core and created only by Alembic raw-SQL revisions in
``apps/api/migrations/versions/``. ``aip-db check-schema`` compares the migrated database with the
tables declared here.
"""

from sqlalchemy import MetaData

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)
