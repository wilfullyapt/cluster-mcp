"""Ceph service layer.

Thin orchestration layer over CephClient. Future home for caching,
business rules, and structured response shaping.
"""

from typing import Any

from clients.ceph import CephClient, ceph_client
from exceptions import CephConnectionError


class CephService:
    def __init__(self, client: CephClient | None = None):
        self.client = client or ceph_client

    def get_health(self) -> dict[str, Any]:
        try:
            return self.client.health()
        except Exception as exc:
            raise CephConnectionError() from exc

    def get_osd_status(self) -> dict[str, Any]:
        return self.client.get_osd_status()

    def get_pool_stats(self) -> dict[str, Any]:
        return self.client.get_pool_stats()

    def get_cephfs_usage(self) -> dict[str, Any]:
        return self.client.get_cephfs_usage()


# Singleton service for routers
ceph_service = CephService()
