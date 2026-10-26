"""Fleet sync — build bridge once, push to all enrolled nodes, optional collect-all.

Control-plane single action so Lamassu need not ritualize per-node updates.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from services.node_inventory import NodeInventory, get_inventory
from services.ssh_transport import ParamikoSSH, SSHTransport
from services.warden_setup import WARDEN_VERSION, UpdateError, update_warden_binary


class FleetSyncError(Exception):
    """Fleet sync cannot start (e.g. empty inventory)."""


@dataclass
class NodeSyncResult:
    node: str
    host: str
    update_ok: bool = False
    collect_ok: bool = False
    warden_version: str | None = None
    lxc_count: int | None = None
    error: str | None = None


@dataclass
class FleetSyncResult:
    success: bool
    built: bool
    version: str
    nodes: list[NodeSyncResult] = field(default_factory=list)
    build_path: str | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "built": self.built,
            "version": self.version,
            "build_path": self.build_path,
            "message": self.message,
            "nodes": [
                {
                    "node": n.node,
                    "host": n.host,
                    "update_ok": n.update_ok,
                    "collect_ok": n.collect_ok,
                    "warden_version": n.warden_version,
                    "lxc_count": n.lxc_count,
                    "error": n.error,
                }
                for n in self.nodes
            ],
            "summary": {
                "total": len(self.nodes),
                "update_ok": sum(1 for n in self.nodes if n.update_ok),
                "collect_ok": sum(1 for n in self.nodes if n.collect_ok),
                "failed": sum(1 for n in self.nodes if n.error),
            },
        }


def default_build_collector(repo_root: Path | None = None) -> Path:
    """Run make collector; return path to binary."""
    root = repo_root or Path(__file__).resolve().parent.parent
    build_dir = root / "wardens" / "build"
    result = subprocess.run(
        ["make", "collector"],
        cwd=build_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise FleetSyncError(
            f"make collector failed:\n{result.stdout}\n{result.stderr}"
        )
    binary = build_dir / "collector"
    if not binary.is_file():
        raise FleetSyncError(f"collector binary missing after build: {binary}")
    return binary


def fleet_sync(
    *,
    inventory: NodeInventory | None = None,
    keys_dir: Path | None = None,
    transport_factory: Callable[[], SSHTransport] | None = None,
    build_fn: Callable[[], Path] | None = None,
    do_build: bool = True,
    do_update: bool = True,
    do_collect: bool = True,
    version: str = WARDEN_VERSION,
) -> FleetSyncResult:
    inv = inventory or get_inventory()
    kdir = keys_dir or (inv.root / "ssh")
    nodes = inv.list_nodes()
    if not nodes:
        raise FleetSyncError("no enrolled nodes")

    factory = transport_factory or ParamikoSSH
    built = False
    build_path: str | None = None

    if do_build:
        bn = build_fn or default_build_collector
        path = bn()
        # Ensure setup/update pick up this binary
        import os

        os.environ["WARDENS_COLLECTOR_BIN"] = str(path)
        built = True
        build_path = str(path)

    results: list[NodeSyncResult] = []
    for rec in nodes:
        nr = NodeSyncResult(node=rec.node, host=rec.host, warden_version=version)
        transport = factory()
        try:
            if do_update:
                try:
                    update_warden_binary(
                        rec.node,
                        inventory=inv,
                        keys_dir=kdir,
                        transport=transport,
                        version=version,
                    )
                    nr.update_ok = True
                    nr.warden_version = version
                except UpdateError as exc:
                    nr.error = f"update: {exc}"
                    results.append(nr)
                    continue

            if do_collect:
                from services.warden_bridge import BridgeError, collect_node

                try:
                    # Fresh transport for collect if previous closed
                    if not getattr(transport, "connected", False):
                        transport = factory()
                    report = collect_node(
                        rec.node,
                        inventory=inv,
                        keys_dir=kdir,
                        transport=transport,
                    )
                    nr.collect_ok = True
                    nr.lxc_count = len(report.get("lxc") or [])
                    nr.warden_version = report.get("warden_version") or nr.warden_version
                except BridgeError as exc:
                    nr.error = (nr.error + "; " if nr.error else "") + f"collect: {exc}"
        finally:
            try:
                transport.close()
            except Exception:  # noqa: BLE001
                pass
        results.append(nr)

    ok = all(n.error is None and (not do_update or n.update_ok) for n in results)
    if do_collect:
        ok = ok and all(n.collect_ok or n.error for n in results)
        # success requires every node fully ok
        ok = all(
            (not do_update or n.update_ok)
            and (not do_collect or n.collect_ok)
            and n.error is None
            for n in results
        )

    msg_parts = []
    if built:
        msg_parts.append(f"built {build_path}")
    msg_parts.append(f"{sum(1 for n in results if n.update_ok)}/{len(results)} updated")
    if do_collect:
        msg_parts.append(f"{sum(1 for n in results if n.collect_ok)}/{len(results)} collected")
    failed = sum(1 for n in results if n.error)
    if failed:
        msg_parts.append(f"{failed} failed")

    return FleetSyncResult(
        success=ok,
        built=built,
        version=version,
        nodes=results,
        build_path=build_path,
        message="; ".join(msg_parts),
    )
