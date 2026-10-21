"""CephClient with Strategy + Adapter pattern.

Primary: Real PVE API calls via existing pve_client session.
Never invents OSD rows or health — failures surface as errors or empty live results.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

import requests

from exceptions import CephConnectionError
from pve_client import get_session
from services.visibility_builder import extract_osds_from_tree


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


class PveApiCephAdapter(CephBackend):
    """Real Ceph data via PVE API (token-authenticated requests session)."""

    def __init__(self):
        self.sess: requests.Session = get_session()
        self.pve_host = os.getenv("PVE_HOST", "https://192.168.0.241:8006").rstrip("/")

    def _get(self, path: str) -> Any:
        try:
            r = self.sess.get(f"{self.pve_host}/api2/json{path}", timeout=30)
            r.raise_for_status()
            return r.json().get("data")
        except Exception as exc:  # noqa: BLE001
            raise CephConnectionError(f"PVE API call failed: {path} -> {exc}") from exc

    def get_health(self) -> dict[str, Any]:
        data = self._get("/cluster/ceph/status") or {}
        if not isinstance(data, dict):
            raise CephConnectionError("Ceph status payload was not an object")
        health = data.get("health", {}) if isinstance(data.get("health"), dict) else {}
        return {
            "status": health.get("status", "unknown"),
            "health": health,
        }

    def get_status(self) -> dict[str, Any]:
        data = self._get("/cluster/ceph/status") or {}
        if not isinstance(data, dict):
            raise CephConnectionError("Ceph status payload was not an object")
        osdmap = data.get("osdmap", {}) if isinstance(data.get("osdmap"), dict) else {}
        monmap = data.get("monmap", {}) if isinstance(data.get("monmap"), dict) else {}
        pgmap = data.get("pgmap", {}) if isinstance(data.get("pgmap"), dict) else {}
        health = data.get("health", {}) if isinstance(data.get("health"), dict) else {}
        return {
            "fsid": data.get("fsid"),
            "health": {"status": health.get("status", "unknown")},
            "mon": {"count": len(monmap.get("mons", []) or [])},
            "osd": {
                "count": osdmap.get("osd_count"),
                "up": osdmap.get("num_up_osds"),
                "in": osdmap.get("num_in_osds"),
            },
            "osdmap": osdmap,
            "monmap": monmap,
            "pgmap": {"pgs_by_state": pgmap.get("pgs_by_state", [])},
            "pgmap_raw": pgmap,
        }

    def get_osds(self) -> list[dict[str, Any]]:
        payloads: list[Any] = []

        # Cluster-level (shape varies by PVE version)
        try:
            data = self._get("/cluster/ceph/osd")
            if data is not None:
                payloads.append(data)
        except CephConnectionError:
            pass

        # Per-node trees (common on Proxmox 8)
        node_names: list[str] = []
        try:
            nodes = self._get("/nodes") or []
            if isinstance(nodes, list):
                node_names = [n.get("node") for n in nodes if isinstance(n, dict) and n.get("node")]
        except CephConnectionError:
            node_names = []

        for node in node_names:
            try:
                node_data = self._get(f"/nodes/{node}/ceph/osd")
                if node_data is not None:
                    payloads.append({"node": node, "data": node_data})
            except CephConnectionError:
                continue

        osds = extract_osds_from_tree(payloads)
        # Live empty is valid — caller must not invent rows.
        return osds

    def get_fs(self) -> dict[str, Any]:
        data = self._get("/cluster/ceph/fs")
        if isinstance(data, list) and data:
            fs = data[0] if isinstance(data[0], dict) else {}
            return {
                "name": fs.get("name", "cephfs"),
                "status": fs.get("status", "unknown"),
                "subvolumes": [],
            }
        if isinstance(data, dict) and data:
            return {
                "name": data.get("name", "cephfs"),
                "status": data.get("status", "unknown"),
                "subvolumes": [],
            }
        return {"name": None, "status": "unavailable", "subvolumes": []}


class CephClient:
    def __init__(self, backend: str = "pve_api", pve_client=None):
        self._impl: CephBackend = PveApiCephAdapter()

    def get_health(self) -> dict[str, Any]:
        return self._impl.get_health()

    def get_status(self) -> dict[str, Any]:
        return self._impl.get_status()

    def get_osds(self) -> list[dict[str, Any]]:
        return self._impl.get_osds()

    def get_fs(self) -> dict[str, Any]:
        return self._impl.get_fs()
