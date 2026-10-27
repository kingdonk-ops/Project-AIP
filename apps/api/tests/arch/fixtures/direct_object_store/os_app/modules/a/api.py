"""Allowed: reach object storage through the facade, never the adapter."""

from os_app.platform.capabilities import get_object_store

__all__ = ["start"]


def start() -> object:
    return get_object_store()
