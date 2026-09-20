"""Custom exceptions for the Proxmox MCP."""

class CephConnectionError(Exception):
    """Raised when a connection to Ceph cannot be established."""
    pass
