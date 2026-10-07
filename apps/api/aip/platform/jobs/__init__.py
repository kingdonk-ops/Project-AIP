"""Background jobs (ADR 0003). Payloads always carry ``tenant_id``; see ``tenant_job``.

A job context has an empty ``asset_path_scope``, which means NO asset access (not unrestricted).
``tenant_job`` raises ``TenantMismatchError`` rather than switch away from an existing tenant.
"""

from aip.platform.jobs.context import TenantMismatchError, tenant_job

__all__ = ["TenantMismatchError", "tenant_job"]
