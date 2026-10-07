"""Breaks no-deep-module-import: reaches into module b's internals."""

from deep_app.modules.b import service


def call() -> str:
    return service.internal()
