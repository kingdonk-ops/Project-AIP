"""Authorisation and invariants for forms (FORMS-01).

Every route declares its permission with ``requires(...)`` (deny by default, ACCESS-01): reading
templates and revisions needs ``form.view``; uploading and editing drafts needs ``form.manage``;
publishing a revision needs ``form.publish``. Rows of another tenant are invisible under RLS, so
they read as 404, never 403.

Immutability is enforced in depth: the service refuses to change a non-draft revision with a 409,
and the ``form_revisions_freeze`` database trigger refuses even a raw ``UPDATE``/``DELETE`` as
``aip_app`` (which also has no ``DELETE`` grant). There are no per-tenant template-count caps in
R1; the lint bounds a single template (256 KB, 500 fields).
"""

from __future__ import annotations

__all__: list[str] = []
