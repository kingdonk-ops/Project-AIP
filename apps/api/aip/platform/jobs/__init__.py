"""Background jobs (ADR 0003). Payloads always carry ``tenant_id``; see ``tenant_job``."""

from aip.platform.jobs.context import tenant_job

__all__ = ["tenant_job"]
