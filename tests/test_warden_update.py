"""Key-based Warden bridge binary refresh (no password)."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.node_inventory import NodeInventory, NodeRecord, reset_inventory_for_tests
from services.warden_setup import UpdateError, update_warden_binary
from tests.test_warden_setup import FakeSSH


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "wardens-data"
    d.mkdir()
    monkeypatch.setenv("WARDENS_DATA_DIR", str(d))
    reset_inventory_for_tests()
    bin_dir = tmp_path / "build"
    bin_dir.mkdir()
    collector = bin_dir / "collector"
    collector.write_bytes(b"\x7fELFnew-bridge")
    monkeypatch.setenv("WARDENS_COLLECTOR_BIN", str(collector))
    inv = NodeInventory(d)
    inv.save(
        NodeRecord(
            node="pvenodeone",
            host="192.168.0.10",
            key_name="warden-pvenodeone",
            collector_path="/opt/wardens/bin/wardens-collector",
            warden_version="0.3.0",
        )
    )
    keys = d / "ssh"
    keys.mkdir()
    (keys / "warden-pvenodeone").write_text("fake-key\n")
    yield d
    reset_inventory_for_tests()


def test_update_pushes_new_binary_over_key_auth(data_dir: Path) -> None:
    ssh = FakeSSH(host="")
    ssh.exec_results = {
        "install -d": (0, "", ""),
        "test -x /opt/wardens/bin/wardens-collector": (0, "", ""),
    }
    result = update_warden_binary(
        "pvenodeone",
        inventory=NodeInventory(data_dir),
        keys_dir=data_dir / "ssh",
        transport=ssh,
    )
    assert result.success is True
    assert result.node == "pvenodeone"
    assert ssh.files["/opt/wardens/bin/wardens-collector"] == b"\x7fELFnew-bridge"
    assert ssh.password is None


def test_update_unknown_node(data_dir: Path) -> None:
    ssh = FakeSSH(host="")
    with pytest.raises(UpdateError, match="not enrolled"):
        update_warden_binary(
            "missing",
            inventory=NodeInventory(data_dir),
            keys_dir=data_dir / "ssh",
            transport=ssh,
        )
