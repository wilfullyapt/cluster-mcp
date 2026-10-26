"""Wardens registration and capabilities router.

MCP side for discovering what each node Warden can see and do.
Collector reports are validated and persisted under WARDENS_DATA_DIR.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from logging_config import get_logger
from models import ActionResponse

router = APIRouter(prefix="/wardens", tags=["Wardens"])
logger = get_logger()

_NODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
_lock = threading.Lock()
_store: WardensStore | None = None


def _safe_node_name(node: str) -> str:
    if not _NODE_RE.match(node):
        raise ValueError(
            "node must be 1-63 chars: alphanumeric, dot, underscore, hyphen"
        )
    return node


class WardenCapabilities(BaseModel):
    node: str
    warden_version: str = Field(..., min_length=1, max_length=64)
    collector_caps: list[str] = Field(default_factory=list)
    runner_allowlist: list[str] = Field(default_factory=list)
    seccomp_profile: str = "none"
    resource_limits: dict[str, Any] = Field(default_factory=dict)

    @field_validator("node")
    @classmethod
    def validate_node(cls, v: str) -> str:
        return _safe_node_name(v)


class LxcVisibilityItem(BaseModel):
    vmid: int = Field(..., ge=0)
    hostname: str = ""
    rootfs: str = ""
    unprivileged: bool = False
    status: str = "unknown"
    mounts: str = ""
    idmap: str = ""


class PermissionDiag(BaseModel):
    target_path: str
    effective_uid: str = ""
    effective_gid: str = ""
    readable: bool = False
    writable: bool = False
    executable: bool = False
    capabilities: str = ""
    mapping_note: str = ""


class HostVisibility(BaseModel):
    """Node host summary from the bridge (load, memory, uptime, kernel, pve)."""

    loadavg_1: float | None = None
    loadavg_5: float | None = None
    loadavg_15: float | None = None
    mem_total_bytes: int | None = None
    mem_available_bytes: int | None = None
    uptime_seconds: float | None = None
    kernel: str = ""
    pve_version: str = ""


class CephfsVisibilityItem(BaseModel):
    subvolume: str = ""
    host_path: str = ""
    container_mount: str = ""
    cephfs_name: str = ""
    owner: str = ""
    permissions: str = ""
    quota_bytes: int | None = None
    used_bytes: int | None = None


class CollectorReport(BaseModel):
    node: str
    warden_version: str = "0.0.0"
    lxc: list[LxcVisibilityItem] = Field(default_factory=list)
    permission: PermissionDiag | None = None
    host: HostVisibility | None = None
    cephfs: list[CephfsVisibilityItem] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("node")
    @classmethod
    def validate_node(cls, v: str) -> str:
        return _safe_node_name(v)


class WardensStore:
    """JSON-file backed store for capabilities and collector reports."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.caps_dir = root / "capabilities"
        self.reports_dir = root / "reports"
        self.caps_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def _caps_path(self, node: str) -> Path:
        return self.caps_dir / f"{node}.json"

    def _report_path(self, node: str) -> Path:
        return self.reports_dir / f"{node}.json"

    def save_capabilities(self, caps: WardenCapabilities) -> None:
        path = self._caps_path(caps.node)
        path.write_text(json.dumps(caps.model_dump(), indent=2) + "\n", encoding="utf-8")

    def load_capabilities(self, node: str) -> dict[str, Any] | None:
        path = self._caps_path(node)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_capabilities(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for path in sorted(self.caps_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                node = data.get("node") or path.stem
                out[node] = data
            except (json.JSONDecodeError, OSError):
                logger.warning("Skipping unreadable capabilities file", path=str(path))
        return out

    def save_report(self, report: CollectorReport) -> None:
        path = self._report_path(report.node)
        path.write_text(json.dumps(report.model_dump(), indent=2) + "\n", encoding="utf-8")

    def load_report(self, node: str) -> dict[str, Any] | None:
        path = self._report_path(node)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_report_nodes(self) -> list[str]:
        return sorted(p.stem for p in self.reports_dir.glob("*.json"))


def _default_data_dir() -> Path:
    raw = os.getenv("WARDENS_DATA_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path(os.getenv("CLUSTERMCP_DATA_DIR", "/var/lib/clustermcp")) / "wardens"


def get_store() -> WardensStore:
    global _store
    with _lock:
        root = _default_data_dir()
        if _store is None or _store.root != root:
            root.mkdir(parents=True, exist_ok=True)
            _store = WardensStore(root)
        return _store


def reset_store_for_tests() -> None:
    """Drop cached store so the next call re-reads WARDENS_DATA_DIR."""
    global _store
    with _lock:
        _store = None


@router.post("/register", response_model=ActionResponse)
def register_warden(caps: WardenCapabilities) -> ActionResponse:
    """Register or update a Warden node's capabilities."""
    get_store().save_capabilities(caps)
    logger.info("Warden registered", node=caps.node, version=caps.warden_version)
    return ActionResponse(success=True, data={"registered": caps.node})


@router.get("/nodes", response_model=ActionResponse)
def list_nodes() -> ActionResponse:
    """List registered Wardens with high-level capability summaries."""
    caps = get_store().list_capabilities()
    summary = {
        node: {
            "warden_version": data.get("warden_version"),
            "collector_caps": data.get("collector_caps", []),
            "runner_allowlist": data.get("runner_allowlist", []),
        }
        for node, data in caps.items()
    }
    return ActionResponse(success=True, data={"nodes": summary})


@router.get("/nodes/{node}/capabilities", response_model=ActionResponse)
def get_node_capabilities(node: str) -> ActionResponse:
    """Return full capabilities report for a specific node."""
    try:
        node = _safe_node_name(node)
    except ValueError as exc:
        return ActionResponse(success=False, error=str(exc))
    data = get_store().load_capabilities(node)
    if data is None:
        return ActionResponse(success=False, error="Node not registered")
    return ActionResponse(success=True, data=data)


@router.get("/capabilities", response_model=ActionResponse)
def global_capabilities() -> ActionResponse:
    """Aggregate view of capabilities across registered Wardens."""
    all_caps: set[str] = set()
    for data in get_store().list_capabilities().values():
        all_caps.update(data.get("collector_caps") or [])
        all_caps.update(data.get("runner_allowlist") or [])
    return ActionResponse(
        success=True,
        data={"all_capabilities": sorted(all_caps)},
    )


@router.post("/collector/report", response_model=ActionResponse)
def receive_collector_report(report: CollectorReport) -> ActionResponse:
    """Accept validated visibility data from a Warden collector."""
    get_store().save_report(report)
    logger.info(
        "Received visibility report",
        node=report.node,
        lxc_count=len(report.lxc),
    )
    return ActionResponse(
        success=True,
        data={
            "stored": report.node,
            "lxc_count": len(report.lxc),
            "fields": list(report.model_dump().keys()),
        },
    )


@router.get("/nodes/{node}/report", response_model=ActionResponse)
def get_node_report(node: str) -> ActionResponse:
    """Return the last collector report for a node."""
    try:
        node = _safe_node_name(node)
    except ValueError as exc:
        return ActionResponse(success=False, error=str(exc))
    data = get_store().load_report(node)
    if data is None:
        return ActionResponse(success=False, error="No report for node")
    return ActionResponse(success=True, data=data)


@router.get("/reports", response_model=ActionResponse)
def list_reports() -> ActionResponse:
    """List nodes that have a stored collector report."""
    return ActionResponse(
        success=True,
        data={"nodes": get_store().list_report_nodes()},
    )


@router.post("/nodes/{node}/collect", response_model=ActionResponse)
def collect_from_node(node: str) -> ActionResponse:
    """MCP-initiated collect: pull report through the on-node Warden bridge.

    The bridge does not call ClusterMCP; ClusterMCP SSHs in with the enrolled
    key and runs the collector (stdout JSON).
    """
    try:
        node = _safe_node_name(node)
    except ValueError as exc:
        return ActionResponse(success=False, error=str(exc))

    from services.warden_bridge import BridgeError, collect_node

    try:
        report = collect_node(node)
    except BridgeError as exc:
        logger.warning("Warden collect failed", node=node, error=str(exc))
        return ActionResponse(success=False, error=str(exc))
    return ActionResponse(success=True, data=report)


@router.get("/enrolled", response_model=ActionResponse)
def list_enrolled_nodes() -> ActionResponse:
    """List nodes enrolled via `cluster setup` (inventory, not push-register)."""
    from services.node_inventory import get_inventory

    rows = [
        {
            "node": n.node,
            "host": n.host,
            "warden_version": n.warden_version,
            "collector_caps": n.collector_caps,
            "auth_method": n.auth_method,
        }
        for n in get_inventory().list_nodes()
    ]
    return ActionResponse(success=True, data={"nodes": rows})


@router.post("/nodes/{node}/update", response_model=ActionResponse)
def update_node_bridge(node: str) -> ActionResponse:
    """Push the MCP host's built bridge binary to an enrolled node (SSH key, no password)."""
    try:
        node = _safe_node_name(node)
    except ValueError as exc:
        return ActionResponse(success=False, error=str(exc))

    from services.node_inventory import get_inventory
    from services.ssh_transport import ParamikoSSH
    from services.warden_setup import UpdateError, update_warden_binary

    inv = get_inventory()
    transport = ParamikoSSH()
    try:
        result = update_warden_binary(
            node,
            inventory=inv,
            keys_dir=inv.root / "ssh",
            transport=transport,
        )
    except UpdateError as exc:
        logger.warning("Warden update failed", node=node, error=str(exc))
        return ActionResponse(success=False, error=str(exc))
    finally:
        transport.close()

    return ActionResponse(
        success=True,
        data={
            "node": result.node,
            "collector_path": result.collector_path,
            "warden_version": result.warden_version,
            "message": result.message,
        },
    )


@router.post("/fleet-sync", response_model=ActionResponse)
def fleet_sync_endpoint(
    build: bool = True,
    update: bool = True,
    collect: bool = True,
) -> ActionResponse:
    """Build bridge (optional), push to all enrolled nodes, optional collect-all."""
    from services.warden_fleet import FleetSyncError, fleet_sync
    from services.warden_setup import WARDEN_VERSION

    try:
        result = fleet_sync(
            do_build=build,
            do_update=update,
            do_collect=collect,
            version=WARDEN_VERSION,
        )
    except FleetSyncError as exc:
        return ActionResponse(success=False, error=str(exc))
    return ActionResponse(success=result.success, data=result.to_dict())


@router.post("/collect-all", response_model=ActionResponse)
def collect_all_enrolled() -> ActionResponse:
    """MCP-initiated collect for every enrolled node (no binary rebuild)."""
    from services.warden_fleet import FleetSyncError, fleet_sync

    try:
        result = fleet_sync(do_build=False, do_update=False, do_collect=True)
    except FleetSyncError as exc:
        return ActionResponse(success=False, error=str(exc))
    return ActionResponse(success=result.success, data=result.to_dict())
