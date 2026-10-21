#!/usr/bin/env python3
"""Render ClusterMCP visibility report PNG from live HTTP probes only.

Usage:
  python3 scripts/render_visibility_report.py --base-url http://192.168.0.233:8000 --out /tmp/report.png

Does not use Hermes memory. Every metric comes from HTTP responses at render time.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Allow running from repo root without install
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.visibility_builder import build_visibility_report  # noqa: E402
from services.visibility_image import render_visibility_image  # noqa: E402


def http_get_json(url: str, timeout: float = 30.0) -> tuple[Any | None, str | None]:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
        payload = json.loads(body)
        if isinstance(payload, dict) and "data" in payload:
            if payload.get("success") is False:
                return None, str(payload.get("error") or payload.get("detail") or "success=false")
            return payload.get("data"), None
        return payload, None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://192.168.0.233:8000", help="ClusterMCP base URL")
    parser.add_argument("--out", required=True, help="Output PNG path")
    parser.add_argument("--json-out", default="", help="Optional JSON report path")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    probe_errors: dict[str, str] = {}

    health, err = http_get_json(f"{base}/health")
    if err:
        probe_errors["mcp_health"] = err
        health = None

    cluster_status, err = http_get_json(f"{base}/cluster/status")
    if err:
        probe_errors["cluster_status"] = err
        cluster_status = []

    nodes, err = http_get_json(f"{base}/cluster/nodes")
    if err:
        probe_errors["nodes"] = err
        nodes = []

    resources, err = http_get_json(f"{base}/cluster/resources")
    if err:
        probe_errors["resources"] = err
        resources = []

    ceph_status, err = http_get_json(f"{base}/ceph/status")
    if err:
        probe_errors["ceph_status"] = err
        ceph_status = {}

    ceph_osds, err = http_get_json(f"{base}/ceph/osds")
    if err:
        probe_errors["ceph_osds"] = err
        ceph_osds = None
    else:
        # Guard: running ClusterMCP still had hardcoded OSD fallbacks.
        # Trust OSD *rows* only when visibility report also had detail OR
        # when values are not the known static fixture. Prefer summary from status.
        # We pass osds through; builder marks detail. Ops note added if fixture-like.
        pass

    # Prefer node metrics from resources type=node + nodes endpoint
    report = build_visibility_report(
        nodes=nodes if isinstance(nodes, list) else [],
        resources=resources if isinstance(resources, list) else [],
        cluster_status=cluster_status if isinstance(cluster_status, list | dict) else [],
        ceph_status=ceph_status if isinstance(ceph_status, dict) else {},
        ceph_osds_raw=ceph_osds,
        mcp_health=health if isinstance(health, dict) else None,
        include_graph_data=True,
        probe_errors=probe_errors,
    )

    # Detect classic hardcoded fallback fixture from old CephClient and strip it
    fixture = [
        (0, 45.2),
        (1, 47.1),
        (2, 44.8),
        (3, 40.0),
        (4, 42.0),
    ]
    osds = report.get("ceph", {}).get("osds") or []
    if osds:
        pairs = [(o.get("id"), round(float(o["usage"]), 1) if o.get("usage") is not None else None) for o in osds]
        if pairs == fixture:
            report["ceph"]["osds"] = []
            summary = report["ceph"]["osd_summary"]
            # Keep up/in/total from status path; clear detail-derived fields.
            summary["detail_available"] = False
            summary["source"] = "ceph_status_osdmap_untrusted_detail_stripped"
            summary["down"] = None
            summary["out"] = None
            report["warnings"].append(
                "Stripped untrusted per-OSD utilization fixture from legacy ClusterMCP fallback"
            )
            report["summary"]["warnings_count"] = len(report["warnings"])
            report["markdown"]["warnings"] = "\n".join(f"- {w}" for w in report["warnings"])
            report["markdown"]["ceph_summary"] = (
                f"**Ceph Health**: {report['ceph'].get('health_status')}\\n"
                f"**MONs**: {report['ceph'].get('mon_count')}\\n"
                f"**OSDs**: total={summary.get('total')} up={summary.get('up')} in={summary.get('in')} "
                f"detail=False source={summary.get('source')}"
            )

    png = render_visibility_image(report)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "out": str(out),
                "bytes": len(png),
                "generated_at": report.get("generated_at"),
                "overall": report.get("overall"),
                "warnings_count": len(report.get("warnings") or []),
                "probe_errors": list(probe_errors.keys()),
                "osd_detail_available": report.get("ceph", {}).get("osd_summary", {}).get("detail_available"),
                "sources": {
                    "health": health is not None,
                    "cluster_status": bool(cluster_status),
                    "nodes": isinstance(nodes, list),
                    "resources": isinstance(resources, list),
                    "ceph_status": isinstance(ceph_status, dict) and bool(ceph_status),
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
