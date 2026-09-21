"""CephService – thin business layer over CephClient."""

from __future__ import annotations

from typing import Any

from clients.ceph_client import CephClient


class CephService:
    def __init__(self, client: CephClient | None = None):
        self.client = client or CephClient()

    def get_health(self) -> dict[str, Any]:
        return self.client.get_health()

    def get_status(self) -> dict[str, Any]:
        return self.client.get_status()

    def get_osds(self) -> list[dict[str, Any]]:
        return self.client.get_osds()

    def get_fs(self) -> dict[str, Any]:
        return self.client.get_fs()
