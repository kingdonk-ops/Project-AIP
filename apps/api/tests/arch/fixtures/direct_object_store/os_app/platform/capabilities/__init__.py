"""The capability facade: it alone imports the adapters (the one allowed path)."""

from os_app.platform.capabilities.adapters.s3 import S3ObjectStore


def get_object_store() -> S3ObjectStore:
    return S3ObjectStore()
