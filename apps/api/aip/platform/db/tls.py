"""Transport security for Postgres and Redis (STACK-07).

One setting pair drives every database client, so asyncpg (the API, the migrator, the probes) and
psycopg (the Procrastinate worker) never disagree:

- ``DB_SSLMODE``: ``disable`` (dev, Coolify), ``require`` (encrypt, no verification) or
  ``verify-full`` (Amazon RDS: verify the chain and the host name);
- ``DB_SSLROOTCERT``: the CA bundle for ``verify-full``. The API image ships the Amazon RDS global
  bundle at :data:`RDS_CA_BUNDLE`, the default.

Redis (Valkey, ElastiCache) uses the URL scheme: ``rediss://`` turns TLS on (with the password in
the URL, for an AUTH token) and ``REDIS_SSL_CA_CERTS`` names its CA bundle.

``AIP_ENV=production`` refuses to start unless ``DB_SSLMODE=verify-full`` and ``REDIS_URL`` (when
set) is ``rediss://``: :func:`check_transport_security` runs at API, worker and migrator startup.
"""

from __future__ import annotations

import os
import ssl
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from aip.platform.db.errors import DatabaseConfigError

__all__ = [
    "DB_SSLMODE_ENV",
    "DB_SSLROOTCERT_ENV",
    "RDS_CA_BUNDLE",
    "REDIS_SSL_CA_CERTS_ENV",
    "DbTls",
    "SslMode",
    "check_transport_security",
    "redis_tls_kwargs",
]

DB_SSLMODE_ENV = "DB_SSLMODE"
DB_SSLROOTCERT_ENV = "DB_SSLROOTCERT"
REDIS_SSL_CA_CERTS_ENV = "REDIS_SSL_CA_CERTS"
RDS_CA_BUNDLE = "/etc/ssl/certs/rds-global-bundle.pem"

SslMode = Literal["disable", "require", "verify-full"]
_MODES: tuple[SslMode, ...] = ("disable", "require", "verify-full")


@dataclass(frozen=True, slots=True)
class DbTls:
    mode: SslMode = "disable"
    root_cert: str | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> DbTls:
        env = os.environ if environ is None else environ
        raw = env.get(DB_SSLMODE_ENV, "").strip().lower() or "disable"
        if raw not in _MODES:
            raise DatabaseConfigError(f"{DB_SSLMODE_ENV} must be one of {', '.join(_MODES)}")
        mode = cast(SslMode, raw)
        root = env.get(DB_SSLROOTCERT_ENV, "").strip() or None
        if mode == "verify-full" and root is None:
            root = RDS_CA_BUNDLE
        return cls(mode, root)

    def asyncpg_ssl(self) -> ssl.SSLContext | bool:
        """asyncpg's ``ssl`` argument: ``False``, or a context that matches the mode."""
        if self.mode == "disable":
            return False
        if self.mode == "require":
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context
        return ssl.create_default_context(cafile=self.root_cert)

    def asyncpg_connect_args(self) -> dict[str, Any]:
        """``connect_args`` for SQLAlchemy's asyncpg dialect.

        Always explicit: asyncpg's own default is ``prefer``, which would use TLS whenever the
        server offers it, so ``disable`` passes ``ssl=False``.
        """
        return {"ssl": self.asyncpg_ssl()}

    def libpq_params(self) -> dict[str, str]:
        """``sslmode`` and ``sslrootcert`` for a libpq/psycopg conninfo."""
        params: dict[str, str] = {"sslmode": self.mode}
        if self.mode == "verify-full" and self.root_cert:
            params["sslrootcert"] = self.root_cert
        return params


def redis_tls_kwargs(url: str, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Extra ``Redis.from_url`` keyword arguments: the CA bundle for a ``rediss://`` URL."""
    env = os.environ if environ is None else environ
    if not url.startswith("rediss://"):
        return {}
    ca = env.get(REDIS_SSL_CA_CERTS_ENV, "").strip()
    return {"ssl_cert_reqs": "required", **({"ssl_ca_certs": ca} if ca else {})}


def check_transport_security(environ: Mapping[str, str] | None = None) -> None:
    """Refuse to start in production without verified TLS to Postgres and TLS to Redis."""
    env = os.environ if environ is None else environ
    tls = DbTls.from_env(env)  # an unknown DB_SSLMODE fails in every environment
    if env.get("AIP_ENV", "") != "production":
        return
    if tls.mode != "verify-full":
        raise DatabaseConfigError(
            f"AIP_ENV=production requires {DB_SSLMODE_ENV}=verify-full (got {tls.mode})"
        )
    redis_url = env.get("REDIS_URL", "")
    if redis_url and not redis_url.startswith("rediss://"):
        raise DatabaseConfigError("AIP_ENV=production requires REDIS_URL to be rediss:// (TLS)")
