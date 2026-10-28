"""TESTING-13 (review 11 M10): the skeleton journeys' events were published and audited.

    docker compose -f infra/docker-compose.yml exec -T api \
        python - < infra/docker/smoke_outbox_audit.py

Runs inside the ``api`` container after the ``@skeleton`` journeys (CI job ``e2e-skeleton``) with
that container's own ``DATABASE_URL`` (``aip_app``, RLS on, bound to each fixture tenant in turn),
so it proves the deployed worker's wiring, not a test double. For up to ``SMOKE_TIMEOUT_S``
seconds (default 60) it waits until, in ``kaefer-demo``:

- at least one ``project.created`` (the walking skeleton), ``workflow.definition_published`` (the
  ``approvals-seed`` one-shot) and ``workflow.transitioned`` (the approvals journeys) exist; and
- every event of those names has ``published_at`` set and an ``audit_log`` row whose
  ``source_event_id`` is the event (the audit module's catch-all subscriber, AUDIT-02), written by
  the worker as ``aip_audit_writer``.

Security-stream events (sign-in, session) land in ``security_audit_events`` instead, so they are not
checked here. Exit 0 when all of that holds, else 1 with what is missing. It reads ids and counts
only, never a payload.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid

from sqlalchemy import text

from aip.platform.db.engine import dispose_engine
from aip.platform.db.session import with_tenant

KAEFER = uuid.UUID("00000000-0000-4000-8000-00000000000a")  # kaefer-demo
REQUIRED = ("project.created", "workflow.definition_published", "workflow.transitioned")
TIMEOUT_S = float(os.environ.get("SMOKE_TIMEOUT_S", "60"))

_REQUIRED_EVENTS = text("""
    SELECT e.event_name,
           count(*) AS total,
           count(*) FILTER (WHERE e.published_at IS NULL) AS unpublished,
           count(*) FILTER (WHERE a.id IS NULL) AS unaudited
      FROM domain_events AS e
      LEFT JOIN audit_log AS a ON a.tenant_id = e.tenant_id AND a.source_event_id = e.id
     WHERE e.event_name = ANY(:names)
     GROUP BY e.event_name
""")


async def _problems() -> list[str]:
    found: list[str] = []
    async with with_tenant(KAEFER) as conn:
        rows = {
            r.event_name: r
            for r in (await conn.execute(_REQUIRED_EVENTS, {"names": list(REQUIRED)})).all()
        }
    for name in REQUIRED:
        row = rows.get(name)
        if row is None:
            found.append(f"kaefer-demo: no {name} event (did the skeleton journeys run?)")
            continue
        if row.unpublished:
            found.append(f"kaefer-demo: {row.unpublished} of {row.total} {name} not published")
        if row.unaudited:
            found.append(
                f"kaefer-demo: {row.unaudited} of {row.total} {name} have no audit_log row"
            )
    return found


async def main() -> int:
    deadline = time.monotonic() + TIMEOUT_S
    try:
        while True:
            found = await _problems()
            if not found or time.monotonic() >= deadline:
                break
            await asyncio.sleep(1)
    finally:
        await dispose_engine()
    for problem in found:
        print(f"FAIL {problem}", file=sys.stderr)
    if found:
        return 1
    print(f"outbox-audit ok: {', '.join(REQUIRED)} published and audited in kaefer-demo")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
