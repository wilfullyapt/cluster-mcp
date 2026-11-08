"""Visibility report router for Stronghold / Discord integration.

Live PVE/Ceph probes only — no recalled or fabricated metrics.
JSON + single PNG image card for Discord/Hermes.

PVE plane failures soft-fail into probe_errors; this route must never kill the
uvicorn worker (bounded timeouts, JSON on all paths).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response

from config import get_pve_host, get_pve_timeout, resolve_app_version
from logging_config import get_logger
from models import ActionResponse
from pve_client import pve_get
from services.ceph_service import CephService
from services.visibility_builder import build_visibility_report
from services.visibility_image import render_visibility_image

router = APIRouter(prefix="/report", tags=["Report"])


def _safe_get(path: str) -> tuple[Any | None, str | None]:
    """Safe PVE GET. Returns (data, error)."""
    data, err = pve_get(path, timeout=get_pve_timeout())
    if err:
        logger = get_logger()
        logger.warning("Failed to fetch %s: %s", path, err)
    return data, err


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
            "version": resolve_app_version(cwd),
            "commit": commit,
            "branch": branch,
            "dirty": dirty,
            "pve_host": get_pve_host(),
        }
    except Exception:  # noqa: BLE001
        return {
            "status": "ok",
            "version": resolve_app_version(),
            "pve_host": get_pve_host(),
        }


def collect_visibility_report(
    include_graph_data: bool = True,
    node_filter: str | None = None,
) -> dict[str, Any]:
    """Gather live probes and build the visibility report dict.

    Never raises for PVE/Ceph/Wardens probe failures — records probe_errors.
    """
    probe_errors: dict[str, str] = {}

    try:
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

        if not ceph_osds_raw:
            tree_bits: list[Any] = []
            node_names: list[str] = []
            if isinstance(nodes, list):
                node_names = [n.get("node") for n in nodes if isinstance(n, dict) and n.get("node")]
            if not node_names and isinstance(cluster_status, list):
                node_names = [
                    n.get("name")
                    for n in cluster_status
                    if isinstance(n, dict) and n.get("type") == "node" and n.get("name")
                ]
            for name in node_names[:8]:
                raw, err = _safe_get(f"/api2/json/nodes/{name}/ceph/osd")
                if err:
                    probe_errors[f"ceph_osds_{name}"] = err
                elif raw is not None:
                    tree_bits.append({"node": name, "data": raw})
            if tree_bits:
                ceph_osds_raw = tree_bits

        wardens_enrolled: list[dict[str, Any]] | dict[str, Any] | None = None
        wardens_reports: dict[str, Any] = {}
        try:
            from services.node_inventory import get_inventory

            wardens_enrolled = [
                {
                    "node": n.node,
                    "host": n.host,
                    "warden_version": n.warden_version,
                    "collector_caps": n.collector_caps,
                    "auth_method": n.auth_method,
                }
                for n in get_inventory().list_nodes()
            ]
        except Exception as exc:  # noqa: BLE001
            probe_errors["wardens_enrolled"] = f"{type(exc).__name__}: {exc}"
            wardens_enrolled = None

        try:
            from routers.wardens import get_store

            store = get_store()
            for name in store.list_report_nodes():
                rep = store.load_report(name)
                if rep is not None:
                    wardens_reports[str(name)] = rep
            if not wardens_enrolled:
                caps = store.list_capabilities()
                if caps:
                    wardens_enrolled = {
                        node: {
                            "warden_version": data.get("warden_version"),
                            "collector_caps": data.get("collector_caps") or [],
                            "runner_allowlist": data.get("runner_allowlist") or [],
                        }
                        for node, data in caps.items()
                    }
        except Exception as exc:  # noqa: BLE001
            probe_errors["wardens_reports"] = f"{type(exc).__name__}: {exc}"

        return build_visibility_report(
            nodes=nodes if isinstance(nodes, list) else [],
            resources=resources if isinstance(resources, list) else [],
            cluster_status=cluster_status if isinstance(cluster_status, list | dict) else [],
            ceph_status=ceph_status if isinstance(ceph_status, dict) else {},
            ceph_osds_raw=ceph_osds_raw,
            mcp_health=_mcp_health_snapshot(),
            wardens_enrolled=wardens_enrolled,
            wardens_reports=wardens_reports or None,
            node_filter=node_filter,
            include_graph_data=include_graph_data,
            probe_errors=probe_errors,
        )
    except Exception as exc:  # noqa: BLE001
        probe_errors["visibility_builder"] = f"{type(exc).__name__}: {exc}"
        return build_visibility_report(
            nodes=[],
            resources=[],
            cluster_status=[],
            ceph_status={},
            ceph_osds_raw=None,
            mcp_health=_mcp_health_snapshot(),
            wardens_enrolled=None,
            wardens_reports=None,
            node_filter=node_filter,
            include_graph_data=include_graph_data,
            probe_errors=probe_errors,
        )


@router.get("/visibility", response_model=ActionResponse)
def visibility_report(include_graph_data: bool = True, node_filter: str | None = None):
    """Generate visibility report from live probes. Soft-fails when PVE is down."""
    logger = get_logger()
    logger.info("Generating visibility report")
    try:
        report_data = collect_visibility_report(
            include_graph_data=include_graph_data,
            node_filter=node_filter,
        )
        return ActionResponse(success=True, data=report_data)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Visibility report generation failed")
        return ActionResponse(
            success=False,
            error=f"{type(exc).__name__}: {exc}",
            data={
                "overall": "down",
                "data_policy": "live_probes_only",
                "probe_errors": {"visibility": f"{type(exc).__name__}: {exc}"},
                "warnings": [f"Visibility builder crash soft-failed: {exc}"],
                "pve_host": get_pve_host(),
            },
        )


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
    except Exception as exc:  # noqa: BLE001
        logger.exception("Visibility report image generation failed")
        return Response(
            content=(
                b'{"success":false,"error":"visibility_image_failed","detail":"'
                + str(exc).encode("utf-8", errors="replace")[:200]
                + b'"}'
            ),
            media_type="application/json",
            status_code=200,
            headers={"X-ClusterMCP-Report-Overall": "down"},
        )
