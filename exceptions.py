"""Custom exceptions for the Proxmox MCP (cluster-mcp)."""

import sys
import traceback

from fastapi import HTTPException

from logging_config import get_logger

logger = get_logger("mcp.exceptions")


class MCPException(Exception):
    """Base exception for all MCP errors.

    Supports optional `action` kwarg for package-wide log funnel.
    When action is provided, the exception automatically logs with
    full context and traceback for observability via /logs endpoints.
    """
    status_code: int = 500
    detail: str = "Internal MCP error"

    def __init__(self, *args, action: str | None = None, **kwargs):
        super().__init__(*args)
        self.action = action
        if action:
            logger.error(
                "mcp_exception_raised",
                action=action,
                exc_type=self.__class__.__name__,
                detail=getattr(self, "detail", str(self)),
                traceback=traceback.format_exc() if any(sys.exc_info()[:2]) else None,
            )


class CephConnectionError(MCPException):
    """Raised when a connection to Ceph cannot be established."""
    status_code = 503
    detail = "Ceph connection error"


class CephPermissionError(MCPException):
    """Raised when the token lacks required Ceph privileges."""
    status_code = 403
    detail = "Ceph permission denied"


class CephNotImplementedError(MCPException):
    """Raised when Ceph functionality is not yet wired (e.g. 404/501 path)."""
    status_code = 501
    detail = "Ceph endpoint not implemented"


def http_exception_from_mcp(exc: Exception) -> HTTPException:
    """Convert an MCP exception into a FastAPI HTTPException."""
    if isinstance(exc, MCPException):
        return HTTPException(status_code=exc.status_code, detail=exc.detail)
    return HTTPException(status_code=500, detail=str(exc))
