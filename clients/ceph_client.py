"""CephClient with Strategy + Adapter pattern.

Primary backend: proxmox-sdk
Fallback: direct librados (optional)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from exceptions import CephConnectionError


class CephBackend(ABC):
    @abstractmethod
    def get_health(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def get_osds(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def get_fs(self) -> dict[str, Any]:
        ...


class ProxmoxSDKCephAdapter(CephBackend):
    """Adapter using proxmox-sdk (preferred)."""

    def __init__(self, pve_client):
        self.pve = pve_client

    def get_health(self) -> dict[str, Any]:
        try:
            # Placeholder - real implementation would call appropriate SDK method
            # For now returns structure matching real ceph -s output shape
            return {
                "status": "HEALTH_OK",
                "health": {"status": "HEALTH_OK", "checks": []},
            }
        except Exception as exc:
            raise CephConnectionError(f"proxmox-sdk health failed: {exc}") from exc

    def get_status(self) -> dict[str, Any]:
        try:
            return {
                "fsid": "placeholder-fsid",
                "health": {"status": "HEALTH_OK"},
                "mon": {"count": 3},
                "osd": {"count": 3, "up": 3, "in": 3},
                "pgmap": {"pgs_by_state": []},
            }
        except Exception as exc:
            raise CephConnectionError(f"proxmox-sdk status failed: {exc}") from exc

    def get_osds(self) -> list[dict[str, Any]]:
        try:
            return [
                {"id": 0, "name": "osd.0", "status": "up", "in": True, "usage": 45.2},
                {"id": 1, "name": "osd.1", "status": "up", "in": True, "usage": 47.1},
                {"id": 2, "name": "osd.2", "status": "up", "in": True, "usage": 44.8},
            ]
        except Exception as exc:
            raise CephConnectionError(f"proxmox-sdk osds failed: {exc}") from exc

    def get_fs(self) -> dict[str, Any]:
        try:
            return {"name": "cephfs", "status": "active", "subvolumes": []}
        except Exception as exc:
            raise CephConnectionError(f"proxmox-sdk fs failed: {exc}") from exc


class CephClient:
    def __init__(self, backend: str = "proxmox_sdk", pve_client=None):
        if backend == "proxmox_sdk":
            self._impl: CephBackend = ProxmoxSDKCephAdapter(pve_client)
        else:
            # Future: DirectLibradosAdapter
            self._impl = ProxmoxSDKCephAdapter(pve_client)

    def get_health(self) -> dict[str, Any]:
        return self._impl.get_health()

    def get_status(self) -> dict[str, Any]:
        return self._impl.get_status()

    def get_osds(self) -> list[dict[str, Any]]:
        return self._impl.get_osds()

    def get_fs(self) -> dict[str, Any]:
        return self._impl.get_fs()
