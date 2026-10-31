"""The inspections module. Only the published interface (``api``) is exported.

Importing it registers the ``inspection`` record resolver and guard facts provider with approvals
(``workflow``), so ``POST /api/v1/approvals/instances`` binds an inspection only to its project.
"""

from . import api, workflow

workflow.install()

__all__ = ["api"]
