"""Unit tests for live-only visibility report builder + image renderer."""

from __future__ import annotations

from services.visibility_builder import build_visibility_report, extract_osds_from_tree
from services.visibility_image import render_visibility_image


def test_extract_osds_from_nested_tree():
    tree = {
        "root": {
            "children": [
                {
                    "type": "host",
                    "name": "pvenodeone",
                    "children": [
                        {"type": "osd", "id": 1, "status": "up", "in": 1, "utilization": 41.5, "host": "pvenodeone"},
                        {"type": "osd", "id": 2, "status": "down", "in": 0, "utilization": 10.0},
                    ],
                }
            ]
        }
    }
    osds = extract_osds_from_tree(tree)
    assert len(osds) == 2
    by_id = {o["id"]: o for o in osds}
    assert by_id[1]["status"] == "up"
    assert by_id[1]["usage"] == 41.5
    assert by_id[2]["status"] == "down"
    assert by_id[2]["in"] is False


def test_build_report_live_only_no_fabricated_osds():
    report = build_visibility_report(
        nodes=[{"node": "pvenodeone", "status": "online", "cpu": 0.1, "mem": 100, "maxmem": 200, "uptime": 3600}],
        resources=[
            {"type": "node", "node": "pvenodeone", "status": "online", "cpu": 0.1, "mem": 100, "maxmem": 200, "uptime": 3600},
            {
                "type": "lxc",
                "vmid": 100,
                "name": "tailscale",
                "node": "pvenodeone",
                "status": "running",
                "cpu": 0.01,
                "mem": 50,
                "maxmem": 512,
                "disk": 1,
                "maxdisk": 8,
                "uptime": 100,
            },
            {"type": "storage", "node": "pvenodeone", "storage": "cephfs", "status": "available", "plugintype": "cephfs", "maxdisk": 1000},
        ],
        cluster_status=[
            {"type": "cluster", "name": "MawiStronghold", "quorate": 1, "nodes": 1, "version": 3},
            {"type": "node", "name": "pvenodeone", "online": 1, "ip": "192.168.0.241", "nodeid": 1},
        ],
        ceph_status={
            "fsid": "abc",
            "health": {"status": "HEALTH_OK"},
            "mon": {"count": 3},
            "osd": {"count": 5, "up": 5, "in": 5},
            "pgmap": {"pgs_by_state": [{"state_name": "active+clean", "count": 65}]},
        },
        ceph_osds_raw=None,  # no detail — must not invent rows
        mcp_health={"version": "test", "commit": "deadbeef", "branch": "main", "dirty": False, "pve_host": "https://pve"},
        probe_errors={},
    )
    assert report["data_policy"] == "live_probes_only"
    assert report["cluster"]["name"] == "MawiStronghold"
    assert report["summary"]["total_containers"] == 1
    assert report["containers"][0]["name"] == "tailscale"
    assert report["ceph"]["osds"] == []
    assert report["ceph"]["osd_summary"]["detail_available"] is False
    assert report["ceph"]["osd_summary"]["up"] == 5
    assert report["ceph"]["pg_states"]["active+clean"] == 65
    assert any("Per-OSD" in w or "OSD" in w for w in report["warnings"])


def test_render_image_png_signature():
    resources = [
        {
            "type": "lxc",
            "vmid": 1,
            "name": "x",
            "node": "n1",
            "status": "running",
            "mem": 1,
            "maxmem": 2,
            "disk": 1,
            "maxdisk": 2,
            "uptime": 1,
            "cpu": 0,
        }
    ]
    report = build_visibility_report(
        nodes=[{"node": "n1", "status": "online", "cpu": 0.2, "mem": 1, "maxmem": 2, "uptime": 10}],
        resources=resources,
        cluster_status=[{"type": "cluster", "name": "demo", "quorate": 1, "nodes": 1}],
        ceph_status={"health": {"status": "HEALTH_OK"}, "osd": {"up": 1, "in": 1}, "pgmap": {"pgs_by_state": []}},
        ceph_osds_raw=[{"type": "osd", "id": 0, "status": "up", "in": True, "utilization": 12.3}],
        mcp_health={"version": "0", "commit": "x", "branch": "main", "dirty": False},
    )
    png = render_visibility_image(report)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1000
