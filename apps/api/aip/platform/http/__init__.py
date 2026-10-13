"""HTTP plumbing shared by every module (error handlers)."""

from aip.platform.http.errors import DomainError, install_error_handlers

__all__ = ["DomainError", "install_error_handlers"]
