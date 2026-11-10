"""CephClient with Strategy + Adapter pattern.

Primary: Real PVE API calls via existing pve_client session.
Never invents OSD rows or health — failures surface as errors or empty live results.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import requests

from config import get_pve_host, get_pve_timeout
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

    @abstractmethod
    def list_subvolumes(self, fs_name: str | None = None, group: str | None = None) -> dict[str, Any]:
        ...

    @abstractmethod
    def get_subvolume(
        self, name: str, fs_name: str | None = None, group: str | None = None
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    def list_cephfs_storages(self) -> dict[str, Any]:
        ...


class PveApiCephAdapter(CephBackend):
    """Real Ceph data via PVE API (token-authenticated requests session)."""

    def __init__(self):
        self.sess: requests.Session = get_session()
        self.pve_host = get_pve_host()
        self.timeout = get_pve_timeout()

    def _get(self, path: str) -> Any:
        try:
            r = self.sess.get(f"{self.pve_host}/api2/json{path}", timeout=self.timeout)
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

        # Per-node trees (common on Proxmox 8) — bound fan-out
        node_names: list[str] = []
        try:
            nodes = self._get("/nodes") or []
            if isinstance(nodes, list):
                node_names = [n.get("node") for n in nodes if isinstance(n, dict) and n.get("node")]
        except CephConnectionError:
            node_names = []

        for node in node_names[:16]:
            try:
                node_data = self._get(f"/nodes/{node}/ceph/osd")
                if node_data is not None:
                    payloads.append({"node": node, "data": node_data})
            except CephConnectionError:
                continue

        return extract_osds_from_tree(payloads)

    def _fs_list(self) -> list[dict[str, Any]]:
        data = self._get("/cluster/ceph/fs")
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict) and data:
            return [data]
        return []

    def _resolve_fs_name(self, fs_name: str | None) -> str | None:
        if fs_name:
            return fs_name
        filesystems = self._fs_list()
        if filesystems:
            name = filesystems[0].get("name")
            if name:
                return str(name)
        return "cephfs"

    def get_fs(self) -> dict[str, Any]:
        filesystems = self._fs_list()
        if not filesystems:
            return {"name": None, "status": "unavailable", "subvolumes": [], "filesystems": []}
        primary = filesystems[0]
        # Best-effort subvolume list (may be empty if API path unsupported)
        subvols: list[dict[str, Any]] = []
        fs_name = primary.get("name") or "cephfs"
        try:
            listed = self.list_subvolumes(fs_name=str(fs_name))
            subvols = list(listed.get("subvolumes") or [])
        except CephConnectionError:
            subvols = []
        return {
            "name": primary.get("name", "cephfs"),
            "status": primary.get("status", "unknown"),
            "metadata": primary,
            "filesystems": filesystems,
            "subvolumes": subvols,
        }

    def _normalize_subvol_row(self, row: Any, *, group: str | None, fs_name: str | None) -> dict[str, Any] | None:
        if isinstance(row, str):
            return {
                "name": row,
                "group": group,
                "fs": fs_name,
                "path": None,
                "quota_bytes": None,
                "used_bytes": None,
            }
        if not isinstance(row, dict):
            return None
        name = row.get("name") or row.get("subvol") or row.get("subvolume")
        if not name:
            return None
        quota = row.get("quota_bytes")
        if quota is None:
            quota = row.get("quota")
        used = row.get("used_bytes")
        if used is None:
            used = row.get("used")
        path = row.get("path") or row.get("full_path")
        return {
            "name": str(name),
            "group": row.get("group") or group,
            "fs": row.get("fs") or fs_name,
            "path": path,
            "quota_bytes": quota,
            "used_bytes": used,
            "raw": row,
        }

    def list_subvolumes(self, fs_name: str | None = None, group: str | None = None) -> dict[str, Any]:
        """List CephFS subvolumes via PVE paths that exist on Stronghold-class clusters.

        Tries several PVE/Ceph endpoint shapes; never invents names when all fail.
        """
        resolved = self._resolve_fs_name(fs_name)
        groups_tried: list[str | None] = [group] if group else [None, "_nogroup", ""]
        errors: list[str] = []
        found: list[dict[str, Any]] = []
        seen: set[str] = set()

        candidate_paths: list[str] = []
        for g in groups_tried:
            if resolved:
                if g:
                    candidate_paths.append(f"/cluster/ceph/fs/{resolved}/subvolume?group={g}")
                    candidate_paths.append(f"/cluster/ceph/fs/{resolved}/subvolume")
                else:
                    candidate_paths.append(f"/cluster/ceph/fs/{resolved}/subvolume")
            # Node-agnostic alternate (some PVE builds)
            if g:
                candidate_paths.append(f"/cluster/ceph/subvolume?fs={resolved}&group={g}")
            else:
                candidate_paths.append(f"/cluster/ceph/subvolume?fs={resolved}")

        # De-dupe path list while preserving order
        uniq_paths: list[str] = []
        for p in candidate_paths:
            if p not in uniq_paths:
                uniq_paths.append(p)

        for path in uniq_paths:
            try:
                data = self._get(path)
            except CephConnectionError as exc:
                errors.append(str(exc))
                continue
            rows: list[Any]
            if isinstance(data, list):
                rows = data
            elif isinstance(data, dict):
                rows = data.get("subvolumes") or data.get("data") or data.get("children") or []
                if not rows and data.get("name"):
                    rows = [data]
            else:
                rows = []
            for row in rows:
                norm = self._normalize_subvol_row(row, group=group, fs_name=resolved)
                if not norm:
                    continue
                key = f"{norm.get('group') or ''}/{norm['name']}"
                if key in seen:
                    continue
                seen.add(key)
                found.append(norm)

        # Optional: enrich each with info when list was name-only
        enriched: list[dict[str, Any]] = []
        for row in found:
            if row.get("path") is not None or row.get("quota_bytes") is not None:
                enriched.append(row)
                continue
            try:
                info = self.get_subvolume(name=row["name"], fs_name=resolved, group=row.get("group") or group)
                merged = {**row, **{k: v for k, v in info.items() if v is not None and k != "raw"}}
                enriched.append(merged)
            except CephConnectionError:
                enriched.append(row)

        return {
            "fs": resolved,
            "group": group,
            "subvolumes": enriched,
            "count": len(enriched),
            "probe_errors": errors[:8],
            "available": True,
        }

    def get_subvolume(
        self, name: str, fs_name: str | None = None, group: str | None = None
    ) -> dict[str, Any]:
        resolved = self._resolve_fs_name(fs_name)
        groups = [group] if group else [None, "_nogroup"]
        errors: list[str] = []
        for g in groups:
            paths = []
            if resolved:
                base = f"/cluster/ceph/fs/{resolved}/subvolume/{name}"
                if g:
                    paths.append(f"{base}?group={g}")
                paths.append(base)
            for path in paths:
                try:
                    data = self._get(path)
                except CephConnectionError as exc:
                    errors.append(str(exc))
                    continue
                if data is None:
                    continue
                if isinstance(data, list) and data:
                    data = data[0]
                if not isinstance(data, dict):
                    continue
                norm = self._normalize_subvol_row(data, group=g, fs_name=resolved) or {
                    "name": name,
                    "group": g,
                    "fs": resolved,
                    "path": data.get("path"),
                    "quota_bytes": data.get("quota") or data.get("quota_bytes"),
                    "used_bytes": data.get("used") or data.get("used_bytes"),
                    "raw": data,
                }
                norm["available"] = True
                return norm
        raise CephConnectionError(
            f"Subvolume info unavailable for name={name!r} fs={resolved!r}: " + "; ".join(errors[:3])
        )

    def list_cephfs_storages(self) -> dict[str, Any]:
        """Return PVE storage entries that appear to be CephFS-backed."""
        data = self._get("/storage")
        rows: list[dict[str, Any]] = []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                stype = str(item.get("type") or item.get("plugintype") or "").lower()
                storage_id = str(item.get("storage") or item.get("name") or "")
                if stype == "cephfs" or storage_id.startswith("cephfs"):
                    rows.append(
                        {
                            "storage": storage_id,
                            "type": stype or "cephfs",
                            "content": item.get("content"),
                            "path": item.get("path"),
                            "nodes": item.get("nodes"),
                            "shared": item.get("shared"),
                            "raw": item,
                        }
                    )
        # Also try cluster resources type=storage for mount path signals
        try:
            resources = self._get("/cluster/resources?type=storage")
        except CephConnectionError:
            resources = None
        if isinstance(resources, list):
            by_id = {r["storage"]: r for r in rows if r.get("storage")}
            for item in resources:
                if not isinstance(item, dict):
                    continue
                storage_id = str(item.get("storage") or "")
                plug = str(item.get("plugintype") or item.get("type") or "").lower()
                if plug != "cephfs" and not storage_id.startswith("cephfs"):
                    continue
                if storage_id in by_id:
                    by_id[storage_id]["node"] = item.get("node")
                    by_id[storage_id]["status"] = item.get("status")
                    by_id[storage_id]["maxdisk"] = item.get("maxdisk")
                    by_id[storage_id]["used"] = item.get("used")
                else:
                    rows.append(
                        {
                            "storage": storage_id,
                            "type": plug or "cephfs",
                            "node": item.get("node"),
                            "status": item.get("status"),
                            "maxdisk": item.get("maxdisk"),
                            "used": item.get("used"),
                            "raw": item,
                        }
                    )
        return {"storages": rows, "count": len(rows), "available": True}


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

    def list_subvolumes(self, fs_name: str | None = None, group: str | None = None) -> dict[str, Any]:
        return self._impl.list_subvolumes(fs_name=fs_name, group=group)

    def get_subvolume(
        self, name: str, fs_name: str | None = None, group: str | None = None
    ) -> dict[str, Any]:
        return self._impl.get_subvolume(name=name, fs_name=fs_name, group=group)

    def list_cephfs_storages(self) -> dict[str, Any]:
        return self._impl.list_cephfs_storages()
