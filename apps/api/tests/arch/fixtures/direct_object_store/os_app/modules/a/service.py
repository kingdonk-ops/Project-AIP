"""Violation: a module importing the S3 adapter internals directly (UPLOADS-02 acceptance)."""

from os_app.platform.capabilities.adapters.s3 import S3ObjectStore

__all__ = ["make"]


def make() -> S3ObjectStore:
    return S3ObjectStore()
