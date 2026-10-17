"""Dev and test seed rows for the login directory (IDENTITY-01).

    python -m aip.modules.identity.seeds

Connects as the table owner through ``DATABASE_MIGRATOR_URL`` (``aip_app`` cannot write the
table). Idempotent. Refuses to run unless ``AIP_ENV`` is ``development``, ``test`` or ``demo``.
The tenant ids are the shared fixture ids from AGENTS.md / ``apps/api/tests/conftest.py``.
"""

from __future__ import annotations

import asyncio
import os
import sys
from uuid import UUID

from sqlalchemy import text

from aip.platform.db.migrator.run import create_migrator_engine

TENANT_A_ID = UUID("00000000-0000-4000-8000-00000000000a")  # kaefer-demo
TENANT_B_ID = UUID("00000000-0000-4000-8000-00000000000b")  # tenant-b

# (kind, key, tenant_id, idp_alias)
DEV_ROWS: tuple[tuple[str, str, UUID, str | None], ...] = (
    ("email_domain", "kaefer.test", TENANT_A_ID, "kaefer-oidc"),
    ("email_domain", "acme.test", TENANT_B_ID, "acme-oidc"),
    ("tenant_slug", "kaefer-demo", TENANT_A_ID, "kaefer-oidc"),
    ("tenant_slug", "tenant-b", TENANT_B_ID, "acme-oidc"),
)

_UPSERT = text(
    """
    INSERT INTO login_directory (kind, key, tenant_id, idp_alias)
    VALUES (:kind, :key, :tenant_id, :idp_alias)
    ON CONFLICT (kind, key) DO UPDATE
      SET tenant_id = EXCLUDED.tenant_id, idp_alias = EXCLUDED.idp_alias
    """
)


class SeedRefusedError(RuntimeError):
    pass


# An allowlist (review 11 L4): an unset, misspelt or new AIP_ENV refuses, like production.
SEED_ENVS = frozenset({"development", "test", "demo"})


async def seed(url: str, *, env: str | None = None) -> int:
    current = env if env is not None else os.environ.get("AIP_ENV", "")
    if current not in SEED_ENVS:
        raise SeedRefusedError(
            f"seeds run only when AIP_ENV is development, test or demo (got {current!r})"
        )
    engine = create_migrator_engine(url)
    try:
        async with engine.begin() as conn:
            for kind, key, tenant_id, alias in DEV_ROWS:
                await conn.execute(
                    _UPSERT, {"kind": kind, "key": key, "tenant_id": tenant_id, "idp_alias": alias}
                )
    finally:
        await engine.dispose()
    return len(DEV_ROWS)


def main() -> int:
    url = os.environ.get("DATABASE_MIGRATOR_URL")
    if not url:
        print("DATABASE_MIGRATOR_URL is not set", file=sys.stderr)
        return 2
    try:
        count = asyncio.run(seed(url))
    except SeedRefusedError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"identity seeds: {count} login_directory rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
