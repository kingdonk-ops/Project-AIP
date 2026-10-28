"""Authorisation and invariants for report templates (REPORTS-01).

Every route declares its permission with ``requires(...)`` (deny by default, ACCESS-01): reading
templates and previewing them needs ``report.template.view``; uploading, publishing, retiring and
deleting a draft needs ``report.template.manage``. Rows of another tenant are invisible under RLS,
so they read as 404 ``TEMPLATE_NOT_FOUND``, never 403.

A template's status only moves forward: draft -> published -> retired. Immutability is enforced in
depth: the service refuses to publish or delete a non-draft with a 409, and the
``report_templates_published_immutable`` trigger refuses even a raw ``UPDATE`` as ``aip_app``
(SQLSTATE 23514) of anything but ``status`` (published -> retired) and ``updated_at``. ``aip_app``
has no ``DELETE`` grant; a retired row is kept so pinned reports can be re-rendered.
"""

from __future__ import annotations

from typing import Final

__all__ = ["ALLOWED_TRANSITIONS", "can_transition"]

ALLOWED_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "draft": frozenset({"published"}),
    "published": frozenset({"retired"}),
    "retired": frozenset(),
}


def can_transition(current: str, new: str) -> bool:
    """Whether a template in ``current`` may move to ``new``."""
    return new in ALLOWED_TRANSITIONS.get(current, frozenset())
