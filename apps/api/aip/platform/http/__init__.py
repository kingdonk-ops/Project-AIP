"""HTTP plumbing shared by every module (error handlers)."""

from aip.platform.http.errors import install_error_handlers

__all__ = ["install_error_handlers"]
