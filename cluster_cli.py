"""cluster CLI — setup and MCP-driven Warden operations.

  cluster setup --ip <node-ip>          # password prompted; never stored
  cluster setup --ip <ip> --password-stdin
  cluster nodes
  cluster collect --node <name>
  cluster update --node <name>          # push new bridge binary via enrolled key
  cluster update --all
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path


def _data_dir() -> Path:
    raw = os.getenv("WARDENS_DATA_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path(os.getenv("CLUSTERMCP_DATA_DIR", "/var/lib/clustermcp")) / "wardens"


def cmd_setup(args: argparse.Namespace) -> int:
    from services.node_inventory import NodeInventory
    from services.ssh_transport import ParamikoSSH
    from services.warden_setup import SetupError, SetupRequest, setup_node

    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    elif os.getenv("CLUSTER_SETUP_PASSWORD"):
        password = os.environ.pop("CLUSTER_SETUP_PASSWORD", "")
    else:
        password = getpass.getpass(f"Password for {args.user}@{args.ip}: ")

    if not password:
        print("error: empty password", file=sys.stderr)
        return 2

    data = _data_dir()
    data.mkdir(parents=True, exist_ok=True)
    transport = ParamikoSSH()
    try:
        result = setup_node(
            SetupRequest(
                host=args.ip,
                password=password,
                ssh_user=args.user,
                ssh_port=args.port,
                node=args.node,
                collect_after=not args.no_collect,
            ),
            transport=transport,
            inventory=NodeInventory(data),
            keys_dir=data / "ssh",
        )
    except SetupError as exc:
        print(f"setup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        password = ""  # noqa: F841
        transport.close()

    payload = {
        "success": result.success,
        "node": result.node,
        "host": result.host,
        "collector_path": result.collector_path,
        "message": result.message,
    }
    if result.initial_report is not None:
        payload["initial_report"] = {
            "node": result.initial_report.get("node"),
            "lxc_count": len(result.initial_report.get("lxc") or []),
            "warden_version": result.initial_report.get("warden_version"),
        }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_nodes(_args: argparse.Namespace) -> int:
    from services.node_inventory import NodeInventory

    inv = NodeInventory(_data_dir())
    rows = [
        {
            "node": n.node,
            "host": n.host,
            "warden_version": n.warden_version,
            "collector_caps": n.collector_caps,
        }
        for n in inv.list_nodes()
    ]
    print(json.dumps({"nodes": rows}, indent=2))
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    from services.warden_bridge import BridgeError, collect_node
    from services.warden_fleet import FleetSyncError, fleet_sync

    if getattr(args, "all", False):
        try:
            result = fleet_sync(do_build=False, do_update=False, do_collect=True)
        except FleetSyncError as exc:
            print(f"collect-all failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.success else 1

    try:
        report = collect_node(args.node)
    except BridgeError as exc:
        print(f"collect failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"success": True, "data": report}, indent=2))
    return 0


def cmd_fleet_sync(args: argparse.Namespace) -> int:
    from services.warden_fleet import FleetSyncError, fleet_sync
    from services.warden_setup import WARDEN_VERSION

    try:
        result = fleet_sync(
            do_build=not args.no_build,
            do_update=not args.no_update,
            do_collect=not args.no_collect,
            version=WARDEN_VERSION,
        )
    except FleetSyncError as exc:
        print(f"fleet-sync failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.success else 1


def cmd_update(args: argparse.Namespace) -> int:
    from services.node_inventory import NodeInventory
    from services.ssh_transport import ParamikoSSH
    from services.warden_setup import UpdateError, update_warden_binary

    data = _data_dir()
    inv = NodeInventory(data)
    keys_dir = data / "ssh"

    if args.all:
        targets = [n.node for n in inv.list_nodes()]
        if not targets:
            print("error: no enrolled nodes", file=sys.stderr)
            return 1
    else:
        targets = [args.node]

    results = []
    rc = 0
    for node in targets:
        transport = ParamikoSSH()
        try:
            result = update_warden_binary(
                node,
                inventory=inv,
                keys_dir=keys_dir,
                transport=transport,
            )
            results.append(
                {
                    "success": True,
                    "node": result.node,
                    "warden_version": result.warden_version,
                    "message": result.message,
                }
            )
        except UpdateError as exc:
            rc = 1
            results.append({"success": False, "node": node, "error": str(exc)})
        finally:
            transport.close()

    print(json.dumps({"results": results}, indent=2))
    return rc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cluster",
        description="ClusterMCP control plane CLI (Wardens setup + MCP-initiated collect).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("setup", help="Enroll a Proxmox node: checks + install Warden bridge")
    s.add_argument("--ip", required=True, help="Node IP or DNS name")
    s.add_argument("--user", default="root", help="SSH user (default root)")
    s.add_argument("--port", type=int, default=22, help="SSH port")
    s.add_argument("--node", default=None, help="Override node name (default: remote hostname -s)")
    s.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read password from stdin (never stored)",
    )
    s.add_argument(
        "--no-collect",
        action="store_true",
        help="Skip initial collect after enroll (default: collect once)",
    )
    s.set_defaults(func=cmd_setup)

    n = sub.add_parser("nodes", help="List enrolled Warden nodes")
    n.set_defaults(func=cmd_nodes)

    c = sub.add_parser("collect", help="Pull a visibility report via the Warden bridge")
    c_group = c.add_mutually_exclusive_group(required=True)
    c_group.add_argument("--node", help="Enrolled node name")
    c_group.add_argument("--all", action="store_true", help="Collect every enrolled node")
    c.set_defaults(func=cmd_collect)

    u = sub.add_parser("update", help="Push rebuilt bridge binary via enrolled SSH key")
    u_group = u.add_mutually_exclusive_group(required=True)
    u_group.add_argument("--node", help="Enrolled node name")
    u_group.add_argument("--all", action="store_true", help="Update every enrolled node")
    u.set_defaults(func=cmd_update)

    f = sub.add_parser(
        "fleet-sync",
        help="Build bridge, push to all enrolled nodes, collect (one control-plane action)",
    )
    f.add_argument("--no-build", action="store_true", help="Skip make collector")
    f.add_argument("--no-update", action="store_true", help="Skip binary push")
    f.add_argument("--no-collect", action="store_true", help="Skip collect-all after push")
    f.set_defaults(func=cmd_fleet_sync)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
