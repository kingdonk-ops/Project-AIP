"""Database platform service (ADR 0002): declared tables, migrator and tenant sessions.

- ``engine``: the one bounded ``AsyncEngine`` connecting as ``aip_app`` (``DATABASE_URL``).
- ``session``: ``with_tenant(tenant)``, the only way application code gets a connection (plus
  ``before_tenant()`` for the pre-tenant sign-in lookup, ADR 0005).
- ``templates``: ``render_template`` for the SQL templates in ``db/templates/``.
- ``migrator``: ``aip-db`` (forward-only Alembic migrations as ``aip_owner``).

Only ``aip.platform.db`` may create SQLAlchemy engines or connections
(``tests/arch/test_db_engine_boundary.py``). This package imports nothing eagerly, so the migrator
image, which ships ``aip.platform.db`` without the rest of the app, still starts.
"""
