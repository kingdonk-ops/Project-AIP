"""SQLAlchemy Core table declarations for __module__ (ADR 0002).

Every table has tenant_id, a uuid PK, timestamps, soft delete (unless append-only) and
FORCE ROW LEVEL SECURITY. Tables arrive with the module's migration.
"""
