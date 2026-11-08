"""Wardens section on visibility report (ported from feat/visibility-wardens-report)."""

from __future__ import annotations

from services.visibility_builder import build_visibility_report


def test_wardens_section_present_when_enrolled():
    report = build_visibility_report(
        nodes=[{"node": "pvenodeone", "status": "online", "cpu": 0.1, "mem": 1, "maxmem": 2, "uptime": 10}],
        resources=[
            {"type": "node", "node": "pvenodeone", "status": "online"},
            {"type": "lxc", "vmid": 102, "name": "immich", "node": "pvenodeone", "status": "running"},
        ],
        cluster_status=[{"type": "cluster", "name": "demo", "quorate": 1, "nodes": 1}],
        ceph_status={"health": {"status": "HEALTH_OK"}, "osd": {"up": 1, "in": 1}, "pgmap": {"pgs_by_state": []}},
        ceph_osds_raw=None,
        mcp_health={"version": "test", "commit": "abc", "branch": "main", "dirty": False},
        wardens_enrolled=[
            {
                "node": "pvenodeone",
                "host": "192.168.0.241",
                "warden_version": "0.5.1",
                "collector_caps": ["lxc:full", "host:summary"],
                "auth_method": "ssh_key_forced",
            }
        ],
        wardens_reports={
            "pvenodeone": {
                "node": "pvenodeone",
                "warden_version": "0.5.1",
                "lxc": [
                    {"vmid": 102, "hostname": "immich", "mounts": "mp0=..."},
                    {"vmid": 102, "hostname": "immich", "mounts": "mp0=..."},  # dup
                ],
                "permission": {"readable": True, "target_path": "/etc/pve/lxc"},
            }
        },
        probe_errors={},
    )
    assert report["wardens"]["available"] is True
    assert report["wardens"]["enrolled_count"] == 1
    assert report["wardens"]["report_count"] == 1
    assert report["summary"]["wardens_enrolled"] == 1
    node = report["wardens"]["nodes"][0]
    assert node["lxc_count"] == 1  # deduped vmids
    assert "wardens_summary" in report["markdown"]


def test_attention_next_for_pve_dns_failure():
    report = build_visibility_report(
        nodes=[],
        resources=[],
        cluster_status=[],
        ceph_status={},
        ceph_osds_raw=None,
        wardens_enrolled=[],
        wardens_reports={},
        probe_errors={
            "nodes": "ConnectionError: Failed to resolve 'pve-01'",
            "resources": "ConnectionError: Failed to resolve 'pve-01'",
        },
    )
    assert report["overall"] == "down"
    assert any("PVE_HOST" in a or "DNS" in a or "plane" in a.lower() for a in report["attention"])
