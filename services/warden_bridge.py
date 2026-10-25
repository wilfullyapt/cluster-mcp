"""MCP pulls visibility through the on-node Warden bridge.

The bridge binary prints one CollectorReport JSON document to stdout.
It does not know ClusterMCP's URL and never initiates contact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from routers.wardens import CollectorReport, get_store
from services.node_inventory import NodeInventory, get_inventory
from services.ssh_transport import ParamikoSSH, SSHTransport


class BridgeError(Exception):
    """Collect/run via bridge failed."""


def _keys_dir(inventory_root: Path) -> Path:
    return inventory_root / "ssh"


def collect_node(
    node: str,
    *,
    inventory: NodeInventory | None = None,
    keys_dir: Path | None = None,
    transport: SSHTransport | None = None,
) -> dict[str, Any]:
    inv = inventory or get_inventory()
    rec = inv.get(node)
    if rec is None:
        raise BridgeError(f"node not enrolled: {node}")

    kdir = keys_dir or _keys_dir(inv.root)
    key_path = kdir / rec.key_name
    if not key_path.is_file():
        raise BridgeError(f"SSH private key missing for {node}: {key_path}")

    owns_transport = transport is None
    ssh: SSHTransport = transport or ParamikoSSH()
    try:
        if owns_transport or not getattr(ssh, "connected", False):
            ssh.connect_key(rec.host, rec.ssh_user, key_path, port=rec.ssh_port)

        # Source env for WARDEN_NODE; binary prints JSON report to stdout
        cmd = (
            f"set -a; "
            f"[ -f /etc/wardens/collector.env ] && . /etc/wardens/collector.env; "
            f"set +a; "
            f"WARDEN_NODE=${{WARDEN_NODE:-{rec.node}}} "
            f"{rec.collector_path}"
        )
        code, out, err = ssh.run(cmd)
        if code != 0:
            raise BridgeError(f"collector exit {code} on {node}: {err.strip() or out.strip()}")

        text = out.strip()
        if not text:
            raise BridgeError(f"collector produced empty stdout on {node}")
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise BridgeError(f"collector stdout is not JSON on {node}: {exc}") from exc

        # Force node identity from inventory (bridge may omit or disagree)
        raw["node"] = rec.node
        report = CollectorReport.model_validate(raw)
        get_store().save_report(report)
        return report.model_dump()
    finally:
        if owns_transport:
            ssh.close()
