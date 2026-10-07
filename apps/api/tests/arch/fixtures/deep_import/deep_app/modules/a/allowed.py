"""Allowed cross-module imports: the other module's package and its ``api``."""

from deep_app.modules import b
from deep_app.modules.b import api
from deep_app.modules.b.api import ping


def call() -> tuple[str, str, str]:
    return b.api.ping(), api.ping(), ping()
