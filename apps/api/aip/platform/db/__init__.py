"""Database platform service (ADR 0002): declared tables, migrator and (later) tenant sessions.

Only ``aip.platform.db`` may create SQLAlchemy engines or connections.
"""
