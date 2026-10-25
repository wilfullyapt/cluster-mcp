"""Durable inventory of enrolled Warden nodes.

Passwords are never accepted or stored here. Ongoing auth is SSH key only.
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_NODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
_lock = threading.Lock()
_cached: NodeInventory | None = None


def _safe_node_name(node: str) -> str:
    if not _NODE_RE.match(node):
        raise ValueError("node must be 1-63 chars: alphanumeric, dot, underscore, hyphen")
    return node


@dataclass
class NodeRecord:
    node: str
    host: str
    ssh_user: str = "root"
    ssh_port: int = 22
    auth_method: str = "ssh_key"
    key_name: str = ""
    collector_path: str = "/opt/wardens/bin/wardens-collector"
    warden_version: str = "0.3.0"
    collector_caps: list[str] = field(default_factory=lambda: ["lxc:full", "permissions:audit"])
    runner_allowlist: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.node = _safe_node_name(self.node)
        if self.auth_method != "ssh_key":
            raise ValueError("only ssh_key auth_method is supported for enrolled nodes")


class NodeInventory:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.nodes_dir = root / "nodes"
        self.nodes_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, node: str) -> Path:
        return self.nodes_dir / f"{_safe_node_name(node)}.json"

    def save(self, record: NodeRecord) -> None:
        # Belt-and-suspenders: never serialize unexpected password attrs
        data = asdict(record)
        for banned in ("password", "ssh_password", "secret", "passwd"):
            data.pop(banned, None)
        path = self._path(record.node)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def get(self, node: str) -> NodeRecord | None:
        path = self._path(node)
        if not path.is_file():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return self._from_dict(raw)

    def list_nodes(self) -> list[NodeRecord]:
        out: list[NodeRecord] = []
        for path in sorted(self.nodes_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                out.append(self._from_dict(raw))
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                continue
        return out

    @staticmethod
    def _from_dict(raw: dict[str, Any]) -> NodeRecord:
        allowed = {
            "node",
            "host",
            "ssh_user",
            "ssh_port",
            "auth_method",
            "key_name",
            "collector_path",
            "warden_version",
            "collector_caps",
            "runner_allowlist",
        }
        cleaned = {k: v for k, v in raw.items() if k in allowed}
        return NodeRecord(**cleaned)


def _default_data_dir() -> Path:
    raw = os.getenv("WARDENS_DATA_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path(os.getenv("CLUSTERMCP_DATA_DIR", "/var/lib/clustermcp")) / "wardens"


def get_inventory() -> NodeInventory:
    global _cached
    with _lock:
        root = _default_data_dir()
        if _cached is None or _cached.root != root:
            root.mkdir(parents=True, exist_ok=True)
            _cached = NodeInventory(root)
        return _cached


def reset_inventory_for_tests() -> None:
    global _cached
    with _lock:
        _cached = None
