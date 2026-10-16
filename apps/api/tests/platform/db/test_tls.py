"""STACK-07: TLS to Postgres and Redis, one setting pair for every client.

Unit tests check the settings and the production guard. Integration tests start a Postgres that
accepts only TLS (``ssl=on``, ``hostssl`` in ``pg_hba``) and a Valkey that listens only on TLS with
``requirepass``, both with a certificate from a throwaway CA generated here, and connect with
``verify-full`` through the same code the API, the worker and the readiness probe use.
"""

from __future__ import annotations

import datetime
import ipaddress
import ssl
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import text

from aip.modules.ops.health import ReadinessChecker
from aip.platform.db.engine import EngineSettings, create_app_engine
from aip.platform.db.errors import DatabaseConfigError
from aip.platform.db.migrator.cli import main as aip_db
from aip.platform.db.tls import RDS_CA_BUNDLE, DbTls, check_transport_security, redis_tls_kwargs
from aip.platform.jobs.app import jobs_conninfo
from tests.fixtures.postgres import _docker_reachable  # pyright: ignore[reportPrivateUsage]

PROD = {"AIP_ENV": "production"}


# --- unit -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "env",
    [
        {**PROD},
        {**PROD, "DB_SSLMODE": "disable"},
        {**PROD, "DB_SSLMODE": "require"},
        {**PROD, "DB_SSLMODE": "verify-full", "REDIS_URL": "redis://valkey:6379/0"},
    ],
)
def test_production_refuses_anything_but_verified_tls(env: dict[str, str]) -> None:
    with pytest.raises(DatabaseConfigError, match="AIP_ENV=production requires"):
        check_transport_security(env)


def test_production_accepts_verify_full_and_rediss() -> None:
    check_transport_security(
        {**PROD, "DB_SSLMODE": "verify-full", "REDIS_URL": "rediss://:tok@cache:6379/0"}
    )
    check_transport_security({**PROD, "DB_SSLMODE": "VERIFY-FULL"})  # no Redis configured


def test_dev_runs_in_plain_text_but_an_unknown_mode_fails_everywhere() -> None:
    check_transport_security({"AIP_ENV": "development", "REDIS_URL": "redis://valkey:6379/0"})
    with pytest.raises(DatabaseConfigError, match="DB_SSLMODE must be one of"):
        check_transport_security({"AIP_ENV": "development", "DB_SSLMODE": "prefer"})


def test_asyncpg_and_psycopg_get_the_same_verify_full_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DB_SSLMODE", "verify-full")
    monkeypatch.delenv("DB_SSLROOTCERT", raising=False)
    monkeypatch.setenv("DATABASE_JOBS_URL", "postgresql://aip_jobs:pw@db:5432/aip")
    tls = DbTls.from_env()
    assert tls.root_cert == RDS_CA_BUNDLE
    context = tls.asyncpg_ssl()
    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    conninfo = psycopg.conninfo.conninfo_to_dict(jobs_conninfo())
    assert (conninfo["sslmode"], conninfo["sslrootcert"]) == ("verify-full", RDS_CA_BUNDLE)


def test_require_encrypts_without_verifying_and_disable_adds_nothing() -> None:
    context = DbTls("require").asyncpg_ssl()
    assert isinstance(context, ssl.SSLContext) and context.verify_mode == ssl.CERT_NONE
    assert DbTls("disable").asyncpg_connect_args() == {}
    assert DbTls("disable").libpq_params() == {"sslmode": "disable"}


def test_redis_tls_options_follow_the_url_scheme() -> None:
    env = {"REDIS_SSL_CA_CERTS": "/certs/ca.pem"}
    assert redis_tls_kwargs("redis://valkey:6379/0", env) == {}
    assert redis_tls_kwargs("rediss://:tok@cache:6379/0", env) == {
        "ssl_cert_reqs": "required",
        "ssl_ca_certs": "/certs/ca.pem",
    }


def test_the_migrator_exits_2_in_production_without_tls(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AIP_ENV", "production")
    monkeypatch.setenv("DB_SSLMODE", "disable")
    assert aip_db(["migrate"]) == 2
    assert "DB_SSLMODE=verify-full" in capsys.readouterr().err


# --- integration: TLS-only Postgres and Valkey ------------------------------------------------


@dataclass(frozen=True)
class Pki:
    ca: Path
    cert: Path
    key: Path


def _pki(directory: Path) -> Pki:
    """A throwaway CA and a server certificate for localhost / 127.0.0.1."""
    now = datetime.datetime.now(datetime.UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "aip-test-ca")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(ca_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    pem = serialization.Encoding.PEM
    pki = Pki(directory / "ca.pem", directory / "server.crt", directory / "server.key")
    pki.ca.write_bytes(ca.public_bytes(pem))
    pki.cert.write_bytes(cert.public_bytes(pem))
    pki.key.write_bytes(
        key.private_bytes(pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    for path in (pki.ca, pki.cert, pki.key):
        path.chmod(0o644)
    return pki


def _require_docker() -> None:
    if not _docker_reachable():
        pytest.skip("Docker is needed for the TLS containers")


def _container(image: str, port: int, certs: Path, command: str) -> Any:
    from testcontainers.core.container import (  # pyright: ignore[reportMissingTypeStubs]
        DockerContainer,
    )

    container: Any = DockerContainer(image)
    container.with_exposed_ports(port)
    container.with_volume_mapping(str(certs), "/certs", "ro")
    container.with_env("POSTGRES_PASSWORD", "postgres")
    container.with_command(command)
    return container


def _wait(check: Any, what: str, timeout_s: float = 90) -> None:
    deadline = time.monotonic() + timeout_s
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            check()
            return
        except Exception as exc:
            last = exc
            time.sleep(1)
    raise RuntimeError(f"{what} did not become ready: {last}")


HBA = "local all all trust\\nhostssl all all all scram-sha-256\\n"


@pytest.fixture(scope="module")
def tls_postgres(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, Pki]]:
    """A Postgres that accepts only TLS, with a non-privileged login role ``probe``."""
    _require_docker()
    certs = tmp_path_factory.mktemp("pg-certs")
    pki = _pki(certs)
    start = (
        'bash -c "cp /certs/server.crt /certs/server.key /tmp/ && chown postgres /tmp/server.key'
        " && chmod 600 /tmp/server.key"
        f" && printf '{HBA}' > /tmp/pg_hba.conf && chown postgres /tmp/pg_hba.conf"
        " && exec docker-entrypoint.sh postgres -c ssl=on -c ssl_cert_file=/tmp/server.crt"
        ' -c ssl_key_file=/tmp/server.key -c hba_file=/tmp/pg_hba.conf"'
    )
    with _container("pgvector/pgvector:pg16", 5432, certs, start) as pg:
        port = pg.get_exposed_port(5432)
        admin = f"host=localhost port={port} user=postgres password=postgres dbname=postgres"

        def ready() -> None:
            with psycopg.connect(f"{admin} sslmode=require", connect_timeout=3) as conn:
                conn.execute("SELECT 1")

        _wait(ready, "TLS Postgres")
        with psycopg.connect(f"{admin} sslmode=require", autocommit=True) as conn:
            conn.execute("CREATE ROLE probe LOGIN PASSWORD 'probe'")
        yield f"postgresql://probe:probe@localhost:{port}/postgres", pki


async def test_the_engine_connects_with_verify_full_and_plain_text_is_refused(
    tls_postgres: tuple[str, Pki], monkeypatch: pytest.MonkeyPatch
) -> None:
    url, pki = tls_postgres
    monkeypatch.setenv("DB_SSLMODE", "verify-full")
    monkeypatch.setenv("DB_SSLROOTCERT", str(pki.ca))
    engine = create_app_engine(EngineSettings(url=url, pool_size=1, max_overflow=0))
    try:
        async with engine.connect() as conn:
            encrypted = (
                await conn.execute(text("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()"))
            ).scalar_one()
        assert encrypted is True
    finally:
        await engine.dispose()

    monkeypatch.setenv("DB_SSLMODE", "disable")
    plain = create_app_engine(EngineSettings(url=url, pool_size=1, max_overflow=0))
    try:
        with pytest.raises(Exception, match="no pg_hba.conf entry|SSL off|rejected"):
            async with plain.connect() as conn:
                await conn.execute(text("SELECT 1"))
    finally:
        await plain.dispose()


def test_the_worker_conninfo_connects_with_verify_full(
    tls_postgres: tuple[str, Pki], monkeypatch: pytest.MonkeyPatch
) -> None:
    url, pki = tls_postgres
    monkeypatch.setenv("DB_SSLMODE", "verify-full")
    monkeypatch.setenv("DB_SSLROOTCERT", str(pki.ca))
    monkeypatch.setenv("DATABASE_JOBS_URL", url)
    with psycopg.connect(jobs_conninfo()) as conn:
        row = conn.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()").fetchone()
    assert row == (True,)


@pytest.fixture(scope="module")
def tls_valkey(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, Pki]]:
    """A Valkey listening only on TLS, with ``requirepass`` (the ElastiCache AUTH shape)."""
    _require_docker()
    certs = tmp_path_factory.mktemp("valkey-certs")
    pki = _pki(certs)
    start = (
        "valkey-server --port 0 --tls-port 6380 --tls-cert-file /certs/server.crt"
        " --tls-key-file /certs/server.key --tls-ca-cert-file /certs/ca.pem"
        " --tls-auth-clients no --requirepass s3cret-token"
    )
    with _container("valkey/valkey:8-alpine", 6380, certs, start) as valkey:
        url = f"rediss://:s3cret-token@localhost:{valkey.get_exposed_port(6380)}/0"
        yield url, pki


async def test_the_readiness_probe_reaches_tls_valkey_with_auth(
    tls_valkey: tuple[str, Pki], monkeypatch: pytest.MonkeyPatch
) -> None:
    url, pki = tls_valkey
    monkeypatch.setenv("REDIS_SSL_CA_CERTS", str(pki.ca))
    checker = ReadinessChecker(database_url=None, redis_url=url)
    deadline = time.monotonic() + 60
    while True:
        try:
            await checker.check_redis()
            break
        except Exception:
            if time.monotonic() > deadline:
                raise
            time.sleep(1)
    # Without the CA the certificate cannot be verified.
    monkeypatch.delenv("REDIS_SSL_CA_CERTS")
    with pytest.raises(Exception):  # noqa: B017 - redis raises its own ConnectionError subclass
        await ReadinessChecker(database_url=None, redis_url=url).check_redis()
