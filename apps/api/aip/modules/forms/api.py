"""Published interface of the forms module (FORMS-01).

Other modules may import only this file. They pass the tenant-bound connection they already hold
from ``with_tenant``, so the read joins their transaction and RLS applies.

``get_revision`` returns a frozen revision (``published`` or ``superseded``) so inspections keep the
exact form they pinned even after a newer revision is published; it never returns a draft or an
unknown id. ``get_current_revision`` returns a template's current published revision.
``lint_template`` and ``LintIssue`` are re-exported for the register/designer and seed tasks
(FORMS-04/05/06) to reuse the same checks.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.forms import repository as repo
from aip.modules.forms.lint import LintIssue, lint_template
from aip.modules.forms.schemas import FormRevisionOut

__all__ = ["FormRevisionOut", "FormsApi", "LintIssue", "lint_template"]

_FROZEN = ("published", "superseded")


class FormsApi:
    """The operations the forms module offers to other modules."""

    async def get_revision(
        self, conn: AsyncConnection, revision_id: UUID
    ) -> FormRevisionOut | None:
        """A frozen revision (``published`` or ``superseded``) in this tenant, else ``None``.

        A draft or an unknown id is ``None``, so a pinned inspection only ever resolves a form that
        can never change under it.
        """
        row = await repo.get_revision_with_template(conn, revision_id)
        if row is None or row["status"] not in _FROZEN:
            return None
        return FormRevisionOut.from_row(row)

    async def get_current_revision(
        self, conn: AsyncConnection, template_id: UUID
    ) -> FormRevisionOut | None:
        """The template's current published revision, or ``None`` (no publish yet, or retired)."""
        template = await repo.get_template(conn, template_id)
        if template is None or template["status"] == "retired":
            return None
        current_id = template["current_revision_id"]
        if current_id is None:
            return None
        row = await repo.get_revision_with_template(conn, current_id)
        return None if row is None else FormRevisionOut.from_row(row)
