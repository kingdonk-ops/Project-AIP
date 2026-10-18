"""The realms for deployed Keycloaks, derived from the dev realms (SECURITY-11 Parts A and D).

The dev realms (``realm-aip.json``, ``realm-mock-idp.json``) are for local dev and CI only: they
carry users with passwords and fall back to public dev client secrets
(``${AIP_API_CLIENT_SECRET:aip_api_dev_only_secret}``). The repository is public, so a deployed
Keycloak must import neither. This script writes the deployed overlay:

- every user with ``credentials`` is dropped (service-account users stay), so the mock IdP has no
  users; the Coolify demo creates them at deploy time from its secrets
  (``infra/coolify/images/mock-idp-users.sh``);
- every ``${..._CLIENT_SECRET:default}`` loses its default. Keycloak leaves an unset placeholder as
  literal text, so the image's entrypoint (``keycloak-entrypoint.sh``) also refuses to start when a
  client secret is unset or a dev value.

Stdlib only: the Coolify Keycloak image runs it in a build stage.
  python3 infra/keycloak/deployed_realms.py <out-dir>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REALMS = ("realm-aip.json", "realm-mock-idp.json")

# A placeholder for a client secret, with its default: ${NAME:default}.
_SECRET_DEFAULT = re.compile(r"\$\{([A-Z0-9_]*_CLIENT_SECRET):[^}]*\}")


def _strip_secret_defaults(value: Any) -> Any:
    if isinstance(value, str):
        return _SECRET_DEFAULT.sub(r"${\1}", value)
    if isinstance(value, list):
        return [_strip_secret_defaults(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, dict):
        return {k: _strip_secret_defaults(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
    return value


def deployed_realm(realm: dict[str, Any]) -> dict[str, Any]:
    """``realm`` without users that have credentials and without client-secret defaults."""
    out: dict[str, Any] = _strip_secret_defaults(realm)
    users = [u for u in out.get("users", []) if "credentials" not in u]
    if users:
        out["users"] = users
    else:
        out.pop("users", None)
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: deployed_realms.py <out-dir>", file=sys.stderr)
        return 2
    out_dir = Path(argv[0])
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in REALMS:
        realm = json.loads((HERE / name).read_text(encoding="utf-8"))
        text = json.dumps(deployed_realm(realm), indent=2, ensure_ascii=False) + "\n"
        (out_dir / name).write_text(text, encoding="utf-8")
        print(f"wrote {out_dir / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
