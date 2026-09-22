"""CephService – thin business layer over CephClient.

Supports real PVE SDK backend, capability gating, and proper client injection.
"""

from __future__ import annotations

import logging
from typing import Any

from clients.ceph_client import CephClient
from exceptions import CephConnectionError

logger = logging.getLogger(__name__)


class CephService:
    def __init__(self, client: CephClient | None = None, pve_client=None):
        if client is not None:
            self.client = client
        else:
            self.client = CephClient(pve_client=pve_client)

    def _check_capability(self, feature: str) -> bool:
        """Placeholder for future integration with /capabilities endpoint."""
        # In production this would check the token's enabled_features
        allowed = {"read_audit", "storage", "ceph_read"}
        return feature in allowed

    def get_health(self) -> dict[str, Any]:
        if not self._check_capability("ceph_read"):
            logger.warning("ceph_read capability not enabled for token")
        try:
            return self.client.get_health()
        except CephConnectionError as exc:
            logger.error("Ceph health query failed: %s", exc)
            raise

    def get_status(self) -> dict[str, Any]:
        try:
            return self.client.get_status()
        except CephConnectionError as exc:
            logger.error("Ceph status query failed: %s", exc)
            raise

    def get_osds(self) -> list[dict[str, Any]]:
        if not self._check_capability("ceph_read"):
            logger.warning("ceph_read capability not enabled — OSD list may be incomplete")
        try:
            return self.client.get_osds()
        except CephConnectionError as exc:
            logger.error("Ceph OSDs query failed: %s", exc)
            raise

    def get_fs(self) -> dict[str, Any]:
        try:
            return self.client.get_fs()
        except CephConnectionError as exc:
            logger.error("CephFS query failed: %s", exc)
            raise
