"""Dedicated Ceph client using proxmox-sdk + optional direct rados bindings.

This accelerates richer Ceph observability beyond the PVE API surface.
Design patterns: Strategy + Adapter for dual backends, Factory for config,
graceful degradation, structured logging.
"""

from __future__ import annotations

import logging
from typing import Any

try:
    from proxmox_sdk import ProxmoxClient  # type: ignore
except ImportError:
    ProxmoxClient = None  # type: ignore

try:
    import rados  # type: ignore
except ImportError:
    rados = None  # type: ignore


logger = logging.getLogger(__name__)


class CephClient:
    """Unified Ceph client for the MCP.

    Prefers proxmox-sdk Ceph facade when available; falls back to direct
    librados when the python3-rados package is installed on the host/LXC.
    Supports explicit backend injection for testing.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        backend: str | None = None,  # "sdk", "librados", or None (auto)
    ) -> None:
        self.config = config or {}
        self._sdk_client = None
        self._rados_cluster = None
        self._backend = backend

        use_sdk = backend in (None, "sdk") and ProxmoxClient is not None
        use_rados = backend in (None, "librados") and rados is not None

        if use_sdk:
            try:
                self._sdk_client = ProxmoxClient(  # type: ignore[call-arg]
                    endpoint=self.config.get("endpoint"),
                    token=self.config.get("token"),
                )
                logger.info("proxmox-sdk Ceph facade initialized")
            except Exception as exc:  # pragma: no cover
                logger.warning("proxmox-sdk init failed: %s", exc)

        if use_rados:
            try:
                conffile = self.config.get("conffile", "/etc/pve/ceph.conf")
                keyring = self.config.get("keyring")
                conf = {"keyring": keyring} if keyring else None
                self._rados_cluster = rados.Rados(conffile=conffile, conf=conf)
                self._rados_cluster.connect()
                logger.info("direct librados cluster connected")
            except Exception as exc:  # pragma: no cover
                logger.warning("librados connect failed: %s", exc)

    # --- Public API ---------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Return structured Ceph health / status."""
        if self._sdk_client:
            try:
                return self._sdk_client.ceph.status()  # type: ignore[attr-defined]
            except Exception as exc:
                logger.error("SDK health failed: %s", exc)

        if self._rados_cluster:
            try:
                fsid = self._rados_cluster.get_fsid()
                stats = self._rados_cluster.get_cluster_stats()
                return {
                    "fsid": fsid,
                    "status": "connected (librados)",
                    "stats": stats,
                }
            except Exception as exc:
                logger.error("librados health failed: %s", exc)

        return {"status": "no client available"}

    def get_osd_status(self) -> dict[str, Any]:
        """Return OSD map / status."""
        if self._sdk_client:
            try:
                return self._sdk_client.ceph.osd()  # type: ignore[attr-defined]
            except Exception as exc:
                logger.warning("SDK OSD call failed: %s", exc)

        if self._rados_cluster:
            return {"status": "librados OSD query not yet implemented"}

        return {"status": "no client available"}

    def get_pool_stats(self) -> dict[str, Any]:
        """Return pool usage and stats."""
        if self._sdk_client:
            try:
                return self._sdk_client.ceph.pool()  # type: ignore[attr-defined]
            except Exception as exc:
                logger.warning("SDK pool call failed: %s", exc)

        if self._rados_cluster:
            try:
                pools = self._rados_cluster.list_pools()
                return {"pools": pools, "count": len(pools)}
            except Exception as exc:
                logger.error("librados pool query failed: %s", exc)

        return {"status": "no client available"}

    def get_cephfs_usage(self) -> dict[str, Any]:
        """Return CephFS usage / df information."""
        if self._sdk_client:
            try:
                return self._sdk_client.ceph.fs()  # type: ignore[attr-defined]
            except Exception as exc:
                logger.warning("SDK CephFS call failed: %s", exc)

        return {"status": "CephFS query requires SDK or cephfs module"}

    def close(self) -> None:
        if self._rados_cluster:
            self._rados_cluster.shutdown()


# Convenience singleton for routers (configured at import time via env)
ceph_client = CephClient()
