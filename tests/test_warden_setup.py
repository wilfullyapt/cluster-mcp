"""cluster setup — password is ephemeral; MCP installs bridge and enrolls node."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from services.node_inventory import NodeInventory, reset_inventory_for_tests
from services.warden_setup import SetupError, SetupRequest, setup_node


@dataclass
class FakeSSH:
    """In-memory SSH stand-in for setup/collect tests."""

    host: str
    user: str = "root"
    password: str | None = None
    connected: bool = False
    files: dict[str, bytes] = field(default_factory=dict)
    commands: list[str] = field(default_factory=list)
    exec_results: dict[str, tuple[int, str, str]] = field(default_factory=dict)
    password_seen: list[str | None] = field(default_factory=list)

    def connect_password(self, host: str, user: str, password: str, port: int = 22) -> None:
        self.host = host
        self.user = user
        self.password_seen.append(password)
        if password != "correct-horse":
            raise OSError("auth failed")
        self.connected = True
        self.password = None  # transport must not retain password

    def connect_key(self, host: str, user: str, key_path: Path, port: int = 22) -> None:
        self.host = host
        self.user = user
        self.connected = True

    def run(self, command: str) -> tuple[int, str, str]:
        self.commands.append(command)
        if command in self.exec_results:
            return self.exec_results[command]
        # prefix match
        for key, val in self.exec_results.items():
            if command.startswith(key) or key in command:
                return val
        return 0, "", ""

    def write_file(self, remote_path: str, data: bytes, mode: int = 0o644) -> None:
        self.files[remote_path] = data

    def read_file(self, remote_path: str) -> bytes:
        return self.files.get(remote_path, b"")

    def close(self) -> None:
        self.connected = False
        self.password = None


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "wardens-data"
    d.mkdir()
    monkeypatch.setenv("WARDENS_DATA_DIR", str(d))
    reset_inventory_for_tests()
    # local fake collector binary
    bin_dir = tmp_path / "build"
    bin_dir.mkdir()
    collector = bin_dir / "collector"
    collector.write_bytes(b"\x7fELFfake-collector")
    monkeypatch.setenv("WARDENS_COLLECTOR_BIN", str(collector))
    yield d
    reset_inventory_for_tests()


def test_setup_enrolls_node_and_does_not_persist_password(data_dir: Path) -> None:
    ssh = FakeSSH(host="")
    ssh.exec_results = {
        "hostname -s": (0, "pvenodeone\n", ""),
        "test -d /etc/pve": (0, "", ""),
        "pveversion": (0, "pve-manager/8.0\n", ""),
        "install -d": (0, "", ""),
        "chmod": (0, "", ""),
        "grep": (1, "", ""),  # key not yet present
        "mkdir": (0, "", ""),
        "cat >>": (0, "", ""),
        "test -x /opt/wardens/bin/wardens-collector": (0, "", ""),
    }

    result = setup_node(
        SetupRequest(host="192.168.0.10", password="correct-horse", ssh_user="root", collect_after=False),
        transport=ssh,
        inventory=NodeInventory(data_dir),
        keys_dir=data_dir / "ssh",
    )

    assert result.node == "pvenodeone"
    assert result.host == "192.168.0.10"
    assert result.success is True
    # password must not linger on transport
    assert ssh.password is None
    assert ssh.password_seen == ["correct-horse"]

    inv = NodeInventory(data_dir)
    rec = inv.get("pvenodeone")
    assert rec is not None
    assert rec.host == "192.168.0.10"
    raw = (data_dir / "nodes" / "pvenodeone.json").read_text()
    assert "correct-horse" not in raw
    assert "password" not in raw

    # key pair created locally; public key installed remotely
    assert (data_dir / "ssh" / "warden-pvenodeone").is_file()
    assert (data_dir / "ssh" / "warden-pvenodeone.pub").is_file()
    # collector binary uploaded
    assert "/opt/wardens/bin/wardens-collector" in ssh.files
    assert ssh.files["/opt/wardens/bin/wardens-collector"].startswith(b"\x7fELF")


def test_setup_rejects_non_pve_host(data_dir: Path) -> None:
    ssh = FakeSSH(host="")
    ssh.exec_results = {
        "hostname -s": (0, "randombox\n", ""),
        "test -d /etc/pve": (1, "", ""),
    }
    with pytest.raises(SetupError, match="not a Proxmox"):
        setup_node(
            SetupRequest(host="10.0.0.9", password="correct-horse", collect_after=False),
            transport=ssh,
            inventory=NodeInventory(data_dir),
            keys_dir=data_dir / "ssh",
        )
    assert NodeInventory(data_dir).list_nodes() == []


def test_setup_auth_failure_does_not_enroll(data_dir: Path) -> None:
    ssh = FakeSSH(host="")
    with pytest.raises(SetupError, match="auth"):
        setup_node(
            SetupRequest(host="10.0.0.9", password="wrong", collect_after=False),
            transport=ssh,
            inventory=NodeInventory(data_dir),
            keys_dir=data_dir / "ssh",
        )
    assert NodeInventory(data_dir).list_nodes() == []
