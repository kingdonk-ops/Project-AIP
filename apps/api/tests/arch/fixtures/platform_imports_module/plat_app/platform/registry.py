"""Breaks platform-never-imports-modules: the platform imports a module."""

from plat_app.modules.a import api


def call() -> str:
    return api.ping()
