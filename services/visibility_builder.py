"""Build Stronghold visibility report payloads from live probe data only.

No Hermes memory, no invented metrics. Missing probes become explicit gaps.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _pct(numer: float | int | None, denom: float | int | None) -> float | None:
    if numer is None or denom is None:
        return None
    try:
        d = float(denom)
        if d <= 0:
            return None
        return float(numer) / d
    except (TypeError, ValueError):
        return None


def _fmt_bytes(n: float | int | None) -> str:
    if n is None:
        return "—"
    try:
        v = float(n)
    except (TypeError, ValueError):
        return "—"
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    for unit in units:
        if v < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(v)} B"
            return f"{v:.1f} {unit}"
        v /= 1024.0
    return "—"


def _fmt_uptime(seconds: float | int | None) -> str:
    try:
        s = int(seconds or 0)
    except (TypeError, ValueError):
        return "—"
    if s <= 0:
        return "—"
    days, rem = divmod(s, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{mins}m")
    return " ".join(parts)


def _fmt_cpu(cpu: float | int | None) -> str:
    if cpu is None:
        return "—"
    try:
        # PVE node cpu is fraction; guest cpu may also be fraction
        v = float(cpu)
        if v <= 1.5:
            return f"{v * 100:.1f}%"
        return f"{v:.1f}%"
    except (TypeError, ValueError):
        return "—"


def extract_osds_from_tree(payload: Any) -> list[dict[str, Any]]:
    """Walk Proxmox Ceph OSD tree/list payloads and return normalized OSD rows."""
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if node is None:
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return

        node_type = str(node.get("type") or "").lower()
        has_osd_id = node.get("id") is not None and (
            node_type == "osd" or str(node.get("name", "")).startswith("osd.") or "utilization" in node or "osd_status" in node
        )
        if node_type == "osd" or (has_osd_id and ("in" in node or "status" in node or "osd_status" in node)):
            osd_id = node.get("id")
            status_raw = node.get("status") or node.get("osd_status") or ""
            if isinstance(status_raw, dict):
                status_raw = status_raw.get("state") or status_raw.get("status") or ""
            in_flag = node.get("in")
            if in_flag is None:
                in_flag = node.get("in_from_map")
            up = False
            if isinstance(status_raw, str) and status_raw:
                up = "up" in status_raw.lower() and "down" not in status_raw.lower().replace("up", "", 1)
            elif node.get("up") is not None:
                up = bool(node.get("up"))
            elif in_flag is not None and node.get("status") is None:
                # weak signal only — keep status unknown unless explicit
                up = False

            usage = node.get("utilization")
            if usage is None:
                usage = node.get("usage")
            if usage is None and node.get("total_space") and node.get("kb_used") is not None:
                usage = _pct(node.get("kb_used"), node.get("total_space"))
                if usage is not None:
                    usage = usage * 100.0

            found.append(
                {
                    "id": osd_id,
                    "name": node.get("name") or (f"osd.{osd_id}" if osd_id is not None else "osd.?"),
                    "status": "up" if up else ("down" if status_raw or in_flag is not None else "unknown"),
                    "in": bool(in_flag) if in_flag is not None else None,
                    "usage": float(usage) if usage is not None else None,
                    "node": node.get("host") or node.get("node"),
                }
            )

        for key in ("children", "nodes", "osds", "root", "data"):
            if key in node:
                walk(node.get(key))

    walk(payload)

    # de-dupe by id/name preserving first rich row
    dedup: dict[str, dict[str, Any]] = {}
    for row in found:
        key = str(row.get("id") if row.get("id") is not None else row.get("name"))
        prev = dedup.get(key)
        if prev is None or (prev.get("usage") is None and row.get("usage") is not None):
            dedup[key] = row
    return sorted(dedup.values(), key=lambda r: (r.get("id") is None, r.get("id") if r.get("id") is not None else 0, str(r.get("name"))))


def build_visibility_report(
    *,
    nodes: list[dict[str, Any]] | None,
    resources: list[dict[str, Any]] | None,
    cluster_status: list[dict[str, Any]] | dict[str, Any] | None,
    ceph_status: dict[str, Any] | None,
    ceph_osds_raw: Any,
    mcp_health: dict[str, Any] | None = None,
    node_filter: str | None = None,
    include_graph_data: bool = True,
    probe_errors: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble report dict strictly from provided live probe payloads."""
    probe_errors = dict(probe_errors or {})
    nodes = list(nodes or [])
    resources = list(resources or [])
    if isinstance(cluster_status, dict):
        cluster_status_list = [cluster_status]
    else:
        cluster_status_list = list(cluster_status or [])
    ceph_status = dict(ceph_status or {})

    if node_filter:
        nodes = [n for n in nodes if n.get("node") == node_filter or n.get("name") == node_filter]
        resources = [r for r in resources if r.get("node") == node_filter]

    # Cluster meta from /cluster/status
    cluster_meta = next((x for x in cluster_status_list if x.get("type") == "cluster"), {}) or {}
    status_nodes = [x for x in cluster_status_list if x.get("type") == "node"]
    status_by_name = {x.get("name"): x for x in status_nodes if x.get("name")}

    # Resource partitions
    qemu = [r for r in resources if r.get("type") == "qemu"]
    lxc = [r for r in resources if r.get("type") == "lxc"]
    storage = [r for r in resources if r.get("type") == "storage"]
    node_resources = [r for r in resources if r.get("type") == "node"]
    nodes_by_name = {n.get("node") or n.get("name"): n for n in nodes if (n.get("node") or n.get("name"))}
    for nr in node_resources:
        name = nr.get("node") or nr.get("name")
        if name and name not in nodes_by_name:
            nodes_by_name[name] = nr

    # Prefer union of names from nodes list + status + resources
    all_node_names = sorted(
        {
            *(n.get("node") for n in nodes if n.get("node")),
            *(n.get("name") for n in status_nodes if n.get("name")),
            *(r.get("node") for r in node_resources if r.get("node")),
        }
    )
    if node_filter:
        all_node_names = [n for n in all_node_names if n == node_filter]

    node_inventory: list[dict[str, Any]] = []
    for name in all_node_names:
        n = nodes_by_name.get(name) or {}
        sn = status_by_name.get(name) or {}
        nres = [r for r in resources if r.get("node") == name]
        status = n.get("status")
        if not status:
            status = "online" if sn.get("online") in (1, True, "1") else ("offline" if sn else "unknown")
        mem_used = n.get("mem") if n.get("mem") is not None else n.get("memused")
        mem_total = n.get("maxmem")
        node_inventory.append(
            {
                "node": name,
                "status": status,
                "ip": sn.get("ip"),
                "nodeid": sn.get("nodeid"),
                "cpu": n.get("cpu"),
                "mem": {"used": mem_used, "total": mem_total},
                "mem_ratio": _pct(mem_used, mem_total),
                "vms_count": len([r for r in nres if r.get("type") == "qemu"]),
                "containers_count": len([r for r in nres if r.get("type") == "lxc"]),
                "storage_count": len([r for r in nres if r.get("type") == "storage"]),
                "uptime": n.get("uptime"),
                "uptime_human": _fmt_uptime(n.get("uptime")),
                "cpu_human": _fmt_cpu(n.get("cpu")),
                "mem_human": f"{_fmt_bytes(mem_used)}/{_fmt_bytes(mem_total)}",
            }
        )

    resource_summary = {
        "total": len(resources),
        "by_type": dict(Counter(r.get("type") for r in resources if r.get("type"))),
        "vms": len(qemu),
        "containers": len(lxc),
        "storage": len(storage),
    }

    # Ceph
    health_block = ceph_status.get("health") if isinstance(ceph_status.get("health"), dict) else {}
    if not health_block and isinstance(ceph_status.get("status"), str):
        health_block = {"status": ceph_status.get("status")}
    ceph_health_status = health_block.get("status") or ceph_status.get("status") or (
        "unavailable" if "ceph_status" in probe_errors else "unknown"
    )

    pg_states_raw = []
    if isinstance(ceph_status.get("pgmap"), dict):
        pg_states_raw = ceph_status["pgmap"].get("pgs_by_state") or []
    pg_state_counts: dict[str, int] = defaultdict(int)
    for pg in pg_states_raw or []:
        if not isinstance(pg, dict):
            continue
        pg_state_counts[str(pg.get("state_name", "unknown"))] += int(pg.get("count") or 0)

    osdmap = ceph_status.get("osdmap") if isinstance(ceph_status.get("osdmap"), dict) else {}
    # Normalized service shape may already flatten osd counts
    flat_osd = ceph_status.get("osd") if isinstance(ceph_status.get("osd"), dict) else {}
    monmap = ceph_status.get("monmap") if isinstance(ceph_status.get("monmap"), dict) else {}
    flat_mon = ceph_status.get("mon") if isinstance(ceph_status.get("mon"), dict) else {}

    mon_count = flat_mon.get("count")
    if mon_count is None and monmap:
        mon_count = len(monmap.get("mons") or [])

    osds = extract_osds_from_tree(ceph_osds_raw)
    osd_source = "osd_tree" if osds else None
    if not osds and flat_osd:
        # summary-only from status — no per-OSD fabrication
        osd_source = "ceph_status_osdmap"
    if not osds and not flat_osd and not osdmap and "ceph_osds" in probe_errors:
        osd_source = "unavailable"

    osd_summary = {
        "total": (
            len(osds)
            if osds
            else flat_osd.get("count")
            if flat_osd.get("count") not in (None, 0)
            else osdmap.get("osd_count")
            if osdmap.get("osd_count") not in (None, 0)
            else (flat_osd.get("up") if flat_osd.get("up") else len(osds))
        ),
        "up": (
            sum(1 for o in osds if o.get("status") == "up")
            if osds
            else flat_osd.get("up") if flat_osd.get("up") is not None else osdmap.get("num_up_osds")
        ),
        "down": (
            sum(1 for o in osds if o.get("status") != "up")
            if osds
            else None
        ),
        "in": (
            sum(1 for o in osds if o.get("in") is True)
            if osds
            else flat_osd.get("in") if flat_osd.get("in") is not None else osdmap.get("num_in_osds")
        ),
        "out": (
            sum(1 for o in osds if o.get("in") is False)
            if osds
            else None
        ),
        "source": osd_source or ("none" if not (osds or flat_osd or osdmap) else "mixed"),
        "detail_available": bool(osds),
    }
    # If total still 0 but up is known, prefer up as total signal without inventing rows
    if (not osd_summary["total"] or osd_summary["total"] == 0) and osd_summary["up"]:
        osd_summary["total"] = osd_summary["up"]

    # Containers detail (live resources only)
    containers = []
    for ct in sorted(lxc, key=lambda x: (x.get("vmid") is None, x.get("vmid") or 0)):
        containers.append(
            {
                "vmid": ct.get("vmid"),
                "name": ct.get("name"),
                "node": ct.get("node"),
                "status": ct.get("status"),
                "cpu": ct.get("cpu"),
                "cpu_human": _fmt_cpu(ct.get("cpu")),
                "mem": {"used": ct.get("mem"), "total": ct.get("maxmem")},
                "mem_human": f"{_fmt_bytes(ct.get('mem'))}/{_fmt_bytes(ct.get('maxmem'))}",
                "disk": {"used": ct.get("disk"), "total": ct.get("maxdisk")},
                "disk_human": f"{_fmt_bytes(ct.get('disk'))}/{_fmt_bytes(ct.get('maxdisk'))}",
                "uptime": ct.get("uptime"),
                "uptime_human": _fmt_uptime(ct.get("uptime")),
                "tags": ct.get("tags"),
            }
        )

    storage_rows = []
    for s in sorted(storage, key=lambda x: (str(x.get("node") or ""), str(x.get("storage") or x.get("name") or ""))):
        used = s.get("used")
        total = s.get("maxdisk") if s.get("maxdisk") is not None else s.get("total")
        storage_rows.append(
            {
                "node": s.get("node"),
                "storage": s.get("storage") or s.get("name"),
                "type": s.get("plugintype") or s.get("type"),
                "status": s.get("status"),
                "used": used,
                "total": total,
                "used_human": _fmt_bytes(used),
                "total_human": _fmt_bytes(total),
                "ratio": _pct(used, total),
            }
        )

    warnings: list[str] = []
    if ceph_health_status not in ("HEALTH_OK", "unknown") and ceph_health_status != "unavailable":
        warnings.append(f"Ceph health: {ceph_health_status}")
    if ceph_health_status == "unavailable":
        warnings.append("Ceph status probe unavailable")
    if osd_summary.get("down"):
        warnings.append(f"{osd_summary['down']} OSD(s) not up")
    if not osd_summary.get("detail_available"):
        if osd_summary.get("up") is not None:
            warnings.append("Per-OSD utilization not available from live OSD tree probe")
        else:
            warnings.append("OSD inventory probe returned no live detail")
    degraded_pgs = sum(v for k, v in pg_state_counts.items() if "degraded" in k.lower() or "incomplete" in k.lower())
    if degraded_pgs:
        warnings.append(f"{degraded_pgs} degraded/incomplete PGs")
    offline_nodes = [n["node"] for n in node_inventory if str(n.get("status", "")).lower() == "offline"]
    if offline_nodes:
        warnings.append(f"Offline nodes: {', '.join(offline_nodes)}")
    unknown_storage = [
        f"{s['node']}/{s['storage']}"
        for s in storage_rows
        if str(s.get("status") or "").lower() in ("unknown", "unavailable", "error", "disabled")
    ]
    if unknown_storage:
        warnings.append(f"Storage status unknown/degraded: {', '.join(unknown_storage)}")
    for key, err in probe_errors.items():
        warnings.append(f"Probe error ({key}): {err}")

    online_count = len([n for n in node_inventory if str(n.get("status", "")).lower() == "online"])

    overall = "ok"
    if offline_nodes or (ceph_health_status not in ("HEALTH_OK", "unknown") and "HEALTH_OK" not in str(ceph_health_status)):
        overall = "degraded"
    if online_count == 0 and node_inventory:
        overall = "down"
    if probe_errors.get("nodes") and probe_errors.get("resources"):
        overall = "down"

    md_sections = {
        "nodes_table": _nodes_to_md(node_inventory),
        "resources_summary": (
            f"**Resources**: {resource_summary['total']} total | "
            f"VMs: {resource_summary['vms']} | Containers: {resource_summary['containers']} | "
            f"Storage: {resource_summary['storage']}"
        ),
        "ceph_summary": _ceph_to_md(ceph_health_status, pg_state_counts, osd_summary, mon_count),
        "warnings": "\n".join(f"- {w}" for w in warnings) if warnings else "No critical warnings.",
        "containers_table": _containers_to_md(containers),
    }

    report: dict[str, Any] = {
        "generated_at": _utc_now(),
        "data_policy": "live_probes_only",
        "overall": overall,
        "cluster": {
            "name": cluster_meta.get("name"),
            "quorate": bool(cluster_meta.get("quorate")) if cluster_meta.get("quorate") is not None else None,
            "nodes_expected": cluster_meta.get("nodes"),
            "version": cluster_meta.get("version"),
        },
        "mcp": mcp_health or None,
        "summary": {
            "nodes_online": online_count,
            "total_nodes": len(node_inventory),
            "total_vms": resource_summary["vms"],
            "total_containers": resource_summary["containers"],
            "ceph_health": ceph_health_status,
            "warnings_count": len(warnings),
            "overall": overall,
        },
        "node_inventory": node_inventory,
        "containers": containers,
        "storage": storage_rows,
        "resource_summary": resource_summary,
        "ceph": {
            "health": health_block or {"status": ceph_health_status},
            "health_status": ceph_health_status,
            "fsid": ceph_status.get("fsid"),
            "mon_count": mon_count,
            "pg_states": dict(pg_state_counts),
            "osd_summary": osd_summary,
            "osds": osds,
        },
        "warnings": warnings,
        "probe_errors": probe_errors,
        "markdown": md_sections,
        "raw_graph_data": {
            "pg_states": dict(pg_state_counts),
            "osd_health": osd_summary,
            "node_cpu_mem": {
                n["node"]: {"cpu": n["cpu"], "mem_used": (n.get("mem") or {}).get("used")}
                for n in node_inventory
            },
        }
        if include_graph_data
        else None,
    }
    return report


def _nodes_to_md(nodes: list[dict]) -> str:
    if not nodes:
        return "No nodes."
    header = (
        "| Node | Status | CPU | Mem Used/Total | VMs | CTs | Storage | Uptime |\n"
        "|------|--------|-----|----------------|-----|-----|---------|--------|\n"
    )
    rows = []
    for n in nodes:
        rows.append(
            f"| {n['node']} | {n['status']} | {n.get('cpu_human') or _fmt_cpu(n.get('cpu'))} | "
            f"{n.get('mem_human') or '—'} | {n['vms_count']} | {n['containers_count']} | "
            f"{n['storage_count']} | {n.get('uptime_human') or n.get('uptime')} |"
        )
    return header + "\n".join(rows)


def _containers_to_md(containers: list[dict]) -> str:
    if not containers:
        return "No containers."
    header = (
        "| VMID | Name | Node | Status | CPU | Mem | Disk | Uptime | Tags |\n"
        "|------|------|------|--------|-----|-----|------|--------|------|\n"
    )
    rows = []
    for c in containers:
        rows.append(
            f"| {c.get('vmid')} | {c.get('name')} | {c.get('node')} | {c.get('status')} | "
            f"{c.get('cpu_human')} | {c.get('mem_human')} | {c.get('disk_human')} | "
            f"{c.get('uptime_human')} | {c.get('tags') or ''} |"
        )
    return header + "\n".join(rows)


def _ceph_to_md(health_status: str, pg_states: dict, osd: dict, mon_count: Any) -> str:
    pg_str = ", ".join(f"{k}: {v}" for k, v in sorted(pg_states.items(), key=lambda x: -x[1])[:5]) or "—"
    return (
        f"**Ceph Health**: {health_status}\n"
        f"**MONs**: {mon_count if mon_count is not None else '—'}\n"
        f"**PG States** (top): {pg_str}\n"
        f"**OSDs**: total={osd.get('total')} up={osd.get('up')} in={osd.get('in')} "
        f"detail={osd.get('detail_available')} source={osd.get('source')}"
    )
