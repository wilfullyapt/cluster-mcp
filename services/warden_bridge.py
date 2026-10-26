"""MCP pulls visibility through the on-node Warden bridge.

Uses forced-command SSH (`collect`) when enrolled with ssh_key_forced.
Falls back to legacy shell one-liner only if forced command is rejected.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from routers.wardens import CollectorReport, get_store
from services.node_inventory import NodeInventory, get_inventory
from services.ssh_transport import ParamikoSSH, SSHTransport
from services.warden_ssh_policy import collect_remote_command, legacy_collect_shell


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

        code, out, err = ssh.run(collect_remote_command())
        if code != 0 and "not allowed" in (err + out).lower():
            code, out, err = ssh.run(legacy_collect_shell(rec.node, rec.collector_path))
        if code != 0:
            raise BridgeError(f"collector exit {code} on {node}: {err.strip() or out.strip()}")

        text = out.strip()
        if not text:
            raise BridgeError(f"collector produced empty stdout on {node}")
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise BridgeError(f"collector stdout is not JSON on {node}: {exc}") from exc

        raw["node"] = rec.node
        report = CollectorReport.model_validate(raw)
        get_store().save_report(report)
        return report.model_dump()
    finally:
        if owns_transport:
            ssh.close()
