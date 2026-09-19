"""Visibility report router for Stronghold / Discord integration.

Provides rich, aggregated, graph-friendly data for on-demand reports.
Focus: per-node inventory, cluster resources, Ceph health/PG/OSD summaries, warnings.
Target: reusable Markdown/JSON generator consumable by Hermes/Discord.
"""

import os
from collections import Counter, defaultdict
from typing import Any

from fastapi import APIRouter, HTTPException

from logging_config import get_logger
from models import ActionResponse
from pve_client import get_session

router = APIRouter(prefix="/report", tags=["Report"])


def _safe_get(url: str) -> dict[str, Any] | None:
    """Safe PVE GET with error logging."""
    try:
        sess = get_session()
        r = sess.get(f"{os.getenv('PVE_HOST', 'https://pve-01:8006')}{url}")
        r.raise_for_status()
        return r.json().get("data")
    except Exception:
        logger = get_logger()
        logger.exception(f"Failed to fetch {url}")
        return None


@router.get("/visibility", response_model=ActionResponse)
def visibility_report(include_graph_data: bool = True, node_filter: str | None = None):
    """
    Generate comprehensive visibility report for Stronghold cluster.

    Aggregates:
    - Per-node status + inventory
    - Cluster resources summary (VMs, containers, storage)
    - Ceph health, PG states (graph-friendly counts), OSD health
    - Actionable warnings
    - Markdown-ready sections for Discord

    Returns structured data + optional raw graph payloads.
    """
    logger = get_logger()
    logger.info("Generating visibility report")

    try:
        # Core fetches
        nodes = _safe_get("/api2/json/nodes") or []
        resources = _safe_get("/api2/json/cluster/resources") or []
        ceph_status = _safe_get("/api2/json/cluster/ceph/status") or {}
        ceph_osds = _safe_get("/api2/json/cluster/ceph/osd") or []

        # Filter nodes if requested
        if node_filter:
            nodes = [n for n in nodes if n.get("node") == node_filter]
            resources = [r for r in resources if r.get("node") == node_filter]

        # Per-node inventory summary
        node_inventory = []
        for node in nodes:
            node_name = node.get("node", "unknown")
            node_resources = [r for r in resources if r.get("node") == node_name]
            vms = [r for r in node_resources if r.get("type") == "qemu"]
            containers = [r for r in node_resources if r.get("type") == "lxc"]
            storages = [r for r in node_resources if r.get("type") == "storage"]

            node_inventory.append({
                "node": node_name,
                "status": node.get("status", "unknown"),
                "cpu": node.get("cpu", 0),
                "mem": {"used": node.get("mem", 0), "total": node.get("maxmem", 0)},
                "vms_count": len(vms),
                "containers_count": len(containers),
                "storage_count": len(storages),
                "uptime": node.get("uptime", 0),
            })

        # Resources summary (by type)
        resource_summary = {
            "total": len(resources),
            "by_type": dict(Counter(r.get("type") for r in resources if r.get("type"))),
            "vms": len([r for r in resources if r.get("type") == "qemu"]),
            "containers": len([r for r in resources if r.get("type") == "lxc"]),
            "storage": len([r for r in resources if r.get("type") == "storage"]),
        }

        # Ceph summaries (graph-friendly)
        ceph_health = ceph_status.get("health", {})
        pg_states_raw = ceph_status.get("pgmap", {}).get("pgs_by_state", []) or []
        pg_state_counts = defaultdict(int)
        for pg in pg_states_raw:
            state = pg.get("state_name", "unknown")
            count = pg.get("count", 0)
            pg_state_counts[state] += count

        osd_summary = {
            "total": len(ceph_osds),
            "up": sum(1 for o in ceph_osds if o.get("status") == "up"),
            "down": sum(1 for o in ceph_osds if o.get("status") != "up"),
            "in": sum(1 for o in ceph_osds if o.get("in") == 1),
            "out": sum(1 for o in ceph_osds if o.get("in") != 1),
        }

        # Warnings
        warnings = []
        if ceph_health.get("status") != "HEALTH_OK":
            warnings.append(f"Ceph health: {ceph_health.get('status', 'unknown')}")
        if osd_summary["down"] > 0:
            warnings.append(f"{osd_summary['down']} OSD(s) down")
        degraded_pgs = sum(v for k, v in pg_state_counts.items() if "degraded" in k.lower() or "incomplete" in k.lower())
        if degraded_pgs > 0:
            warnings.append(f"{degraded_pgs} degraded/incomplete PGs")
        offline_nodes = [n["node"] for n in node_inventory if n["status"] != "online"]
        if offline_nodes:
            warnings.append(f"Offline nodes: {', '.join(offline_nodes)}")

        # Markdown-ready sections (for Discord/Hermes)
        md_sections = {
            "nodes_table": _nodes_to_md(node_inventory),
            "resources_summary": _resources_to_md(resource_summary),
            "ceph_summary": _ceph_to_md(ceph_health, pg_state_counts, osd_summary),
            "warnings": "\n".join(f"- {w}" for w in warnings) if warnings else "No critical warnings.",
        }

        report_data = {
            "summary": {
                "nodes_online": len([n for n in node_inventory if n["status"] == "online"]),
                "total_nodes": len(node_inventory),
                "total_vms": resource_summary["vms"],
                "total_containers": resource_summary["containers"],
                "ceph_health": ceph_health.get("status", "unknown"),
                "warnings_count": len(warnings),
            },
            "node_inventory": node_inventory,
            "resource_summary": resource_summary,
            "ceph": {
                "health": ceph_health,
                "pg_states": dict(pg_state_counts),  # graph-friendly
                "osd_summary": osd_summary,
            },
            "warnings": warnings,
            "markdown": md_sections,  # ready for Discord embed
            "raw_graph_data": {
                "pg_states": dict(pg_state_counts),
                "osd_health": osd_summary,
                "node_cpu_mem": {n["node"]: {"cpu": n["cpu"], "mem_used": n["mem"]["used"]} for n in node_inventory},
            } if include_graph_data else None,
        }

        return ActionResponse(success=True, data=report_data)

    except Exception:
        logger.exception("Visibility report generation failed")
        raise HTTPException(500, detail="Failed to generate visibility report")


def _nodes_to_md(nodes: list[dict]) -> str:
    """Simple Markdown table for nodes."""
    if not nodes:
        return "No nodes."
    header = (
        "| Node | Status | CPU | Mem Used/Total | VMs | CTs | Storage | Uptime |\n"
        "|------|--------|-----|----------------|-----|-----|---------|--------|\n"
    )
    rows = []
    for n in nodes:
        mem = f"{n['mem']['used']}/{n['mem']['total']}"
        row = (
            f"| {n['node']} | {n['status']} | {n['cpu']:.1%} | {mem} | "
            f"{n['vms_count']} | {n['containers_count']} | {n['storage_count']} | {n['uptime']} |"
        )
        rows.append(row)
    return header + "\n".join(rows)


def _resources_to_md(summary: dict) -> str:
    return (
        f"**Resources**: {summary['total']} total | "
        f"VMs: {summary['vms']} | Containers: {summary['containers']} | "
        f"Storage: {summary['storage']} "
    )


def _ceph_to_md(health: dict, pg_states: dict, osd: dict) -> str:
    pg_str = ", ".join(f"{k}: {v}" for k, v in sorted(pg_states.items(), key=lambda x: -x[1])[:5])
    return (
        f"**Ceph Health**: {health.get('status', 'unknown')}\n"
        f"**PG States** (top): {pg_str}\n"
        f"**OSDs**: {osd['total']} total | Up: {osd['up']} | Down: {osd['down']} | In: {osd['in']} | Out: {osd['out']}"
    )
