"""Custom exceptions for the Proxmox MCP (cluster-mcp)."""

from fastapi import HTTPException


class MCPException(Exception):
    """Base exception for all MCP errors."""
    status_code: int = 500
    detail: str = "Internal MCP error"


class CephConnectionError(MCPException):
    """Raised when a connection to Ceph cannot be established."""
    status_code = 503
    detail = "Ceph connection error"


class CephPermissionError(MCPException):
    """Raised when the token lacks required Ceph privileges."""
    status_code = 403
    detail = "Ceph permission denied"


def http_exception_from_mcp(exc: Exception) -> HTTPException:
    """Convert an MCP exception into a FastAPI HTTPException."""
    if isinstance(exc, MCPException):
        return HTTPException(status_code=exc.status_code, detail=exc.detail)
    return HTTPException(status_code=500, detail=str(exc))
