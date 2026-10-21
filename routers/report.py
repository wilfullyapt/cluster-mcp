"""Visibility report router for Stronghold / Discord integration.

Live PVE/Ceph probes only — no recalled or fabricated metrics.
JSON + single PNG image card for Discord/Hermes.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Response

from logging_config import get_logger
from models import ActionResponse
from pve_client import get_session
from services.ceph_service import CephService
from services.visibility_builder import build_visibility_report
from services.visibility_image import render_visibility_image

router = APIRouter(prefix="/report", tags=["Report"])


def _pve_host() -> str:
    return os.getenv("PVE_HOST", "https://pve-01:8006").rstrip("/")


def _safe_get(path: str) -> tuple[Any | None, str | None]:
    """Safe PVE GET. Returns (data, error)."""
    try:
        sess = get_session()
        r = sess.get(f"{_pve_host()}{path}", timeout=30)
        r.raise_for_status()
        payload = r.json()
        return payload.get("data"), None
    except Exception as exc:  # noqa: BLE001 — probe boundary
        logger = get_logger()
        logger.exception("Failed to fetch %s", path)
        return None, f"{type(exc).__name__}: {exc}"


def _mcp_health_snapshot() -> dict[str, Any] | None:
    """Best-effort local health fields without circular HTTP."""
    try:
        import subprocess
        from pathlib import Path

        cwd = Path(__file__).resolve().parents[1]
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=cwd, text=True, timeout=5
        ).strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd, text=True, timeout=5
        ).strip()
        dirty = (
            subprocess.run(["git", "diff", "--quiet"], cwd=cwd, capture_output=True, timeout=5).returncode
            != 0
        )
        return {
            "status": "ok",
            "version": os.getenv("CLUSTERMCP_VERSION", "0.8.0-dev"),
            "commit": commit,
            "branch": branch,
            "dirty": dirty,
            "pve_host": _pve_host(),
        }
    except Exception:  # noqa: BLE001
        return {"status": "ok", "version": os.getenv("CLUSTERMCP_VERSION", "0.8.0-dev"), "pve_host": _pve_host()}


def collect_visibility_report(
    include_graph_data: bool = True,
    node_filter: str | None = None,
) -> dict[str, Any]:
    """Gather live probes and build the visibility report dict."""
    probe_errors: dict[str, str] = {}

    nodes, err = _safe_get("/api2/json/nodes")
    if err:
        probe_errors["nodes"] = err
        nodes = []

    resources, err = _safe_get("/api2/json/cluster/resources")
    if err:
        probe_errors["resources"] = err
        resources = []

    cluster_status, err = _safe_get("/api2/json/cluster/status")
    if err:
        probe_errors["cluster_status"] = err
        cluster_status = []

    # Prefer CephService (normalized) but keep raw tree attempts for OSD detail
    ceph_status: dict[str, Any] = {}
    ceph_osds_raw: Any = None
    try:
        svc = CephService()
        try:
            ceph_status = svc.get_status() or {}
        except Exception as exc:  # noqa: BLE001
            probe_errors["ceph_status"] = f"{type(exc).__name__}: {exc}"
            raw_status, err = _safe_get("/api2/json/cluster/ceph/status")
            if err:
                probe_errors["ceph_status_raw"] = err
            else:
                ceph_status = raw_status or {}
        try:
            ceph_osds_raw = svc.get_osds()
        except Exception as exc:  # noqa: BLE001
            probe_errors["ceph_osds"] = f"{type(exc).__name__}: {exc}"
            ceph_osds_raw = None
    except Exception as exc:  # noqa: BLE001
        probe_errors["ceph_service"] = f"{type(exc).__name__}: {exc}"
        raw_status, err = _safe_get("/api2/json/cluster/ceph/status")
        if err:
            probe_errors["ceph_status"] = err
        else:
            ceph_status = raw_status or {}
        raw_osds, err = _safe_get("/api2/json/cluster/ceph/osd")
        if err:
            probe_errors["ceph_osds"] = err
        else:
            ceph_osds_raw = raw_osds

    # Always try raw node OSD trees to recover detail when service list is empty
    if not ceph_osds_raw:
        tree_bits: list[Any] = []
        node_names = []
        if isinstance(nodes, list):
            node_names = [n.get("node") for n in nodes if n.get("node")]
        if not node_names and isinstance(cluster_status, list):
            node_names = [n.get("name") for n in cluster_status if n.get("type") == "node" and n.get("name")]
        for name in node_names:
            raw, err = _safe_get(f"/api2/json/nodes/{name}/ceph/osd")
            if err:
                probe_errors[f"ceph_osds_{name}"] = err
            elif raw is not None:
                tree_bits.append({"node": name, "data": raw})
        if tree_bits:
            ceph_osds_raw = tree_bits

    return build_visibility_report(
        nodes=nodes if isinstance(nodes, list) else [],
        resources=resources if isinstance(resources, list) else [],
        cluster_status=cluster_status if isinstance(cluster_status, (list, dict)) else [],
        ceph_status=ceph_status if isinstance(ceph_status, dict) else {},
        ceph_osds_raw=ceph_osds_raw,
        mcp_health=_mcp_health_snapshot(),
        node_filter=node_filter,
        include_graph_data=include_graph_data,
        probe_errors=probe_errors,
    )


@router.get("/visibility", response_model=ActionResponse)
def visibility_report(include_graph_data: bool = True, node_filter: str | None = None):
    """
    Generate comprehensive visibility report for Stronghold cluster from live probes.

    Returns structured data + Markdown sections. Does not invent missing metrics.
    """
    logger = get_logger()
    logger.info("Generating visibility report")
    try:
        report_data = collect_visibility_report(
            include_graph_data=include_graph_data,
            node_filter=node_filter,
        )
        return ActionResponse(success=True, data=report_data)
    except Exception:
        logger.exception("Visibility report generation failed")
        raise HTTPException(500, detail="Failed to generate visibility report") from None


@router.get("/visibility.png")
def visibility_report_image(node_filter: str | None = None):
    """Single PNG status card built only from live visibility probes."""
    logger = get_logger()
    logger.info("Generating visibility report image")
    try:
        report_data = collect_visibility_report(include_graph_data=False, node_filter=node_filter)
        png = render_visibility_image(report_data)
        headers = {
            "Cache-Control": "no-store",
            "X-ClusterMCP-Report-Generated-At": str(report_data.get("generated_at", "")),
            "X-ClusterMCP-Report-Overall": str(report_data.get("overall", "")),
            "X-ClusterMCP-Data-Policy": "live_probes_only",
        }
        return Response(content=png, media_type="image/png", headers=headers)
    except Exception:
        logger.exception("Visibility report image generation failed")
        raise HTTPException(500, detail="Failed to generate visibility report image") from None
