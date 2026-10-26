"""MCP-initiated collect via Warden bridge (SSH key → remote collector stdout)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from routers import wardens as wardens_mod
from services.node_inventory import NodeInventory, NodeRecord, reset_inventory_for_tests
from services.warden_bridge import BridgeError, collect_node
from tests.test_warden_setup import FakeSSH

SAMPLE_REPORT = {
    "node": "pvenodeone",
    "warden_version": "0.3.0",
    "lxc": [{"vmid": 100, "hostname": "seneschal", "rootfs": "x", "unprivileged": True, "status": "unknown"}],
    "permission": {
        "target_path": "/etc/pve/lxc",
        "effective_uid": "0",
        "effective_gid": "0",
        "readable": True,
        "writable": True,
        "executable": True,
        "capabilities": "mode=755",
        "mapping_note": "ok",
    },
}


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "wardens-data"
    d.mkdir()
    monkeypatch.setenv("WARDENS_DATA_DIR", str(d))
    reset_inventory_for_tests()
    wardens_mod.reset_store_for_tests()
    inv = NodeInventory(d)
    inv.save(
        NodeRecord(
            node="pvenodeone",
            host="192.168.0.10",
            ssh_user="root",
            ssh_port=22,
            auth_method="ssh_key",
            key_name="warden-pvenodeone",
            collector_path="/opt/wardens/bin/wardens-collector",
        )
    )
    keys = d / "ssh"
    keys.mkdir()
    (keys / "warden-pvenodeone").write_text("fake-key\n")
    yield d
    reset_inventory_for_tests()
    wardens_mod.reset_store_for_tests()


def test_collect_parses_stdout_json_and_stores_report(data_dir: Path) -> None:
    ssh = FakeSSH(host="")
    payload = json.dumps(SAMPLE_REPORT)
    ssh.exec_results = {
               "install -d": (0, "", ""),
               "test -x /opt/wardens/bin/wardens-collector": (0, "", ""),
               "install-binary": (0, '{"ok":true}\n', ""),
               "collect": (0, payload + "\n", "collector stderr ok\n"),
               "/opt/wardens/bin/wardens-collector": (0, payload + "\n", "collector stderr ok\n"),
           }
    report = collect_node(
        "pvenodeone",
        inventory=NodeInventory(data_dir),
        keys_dir=data_dir / "ssh",
        transport=ssh,
    )
    assert report["node"] == "pvenodeone"
    assert report["lxc"][0]["vmid"] == 100
    # stored via wardens store
    stored = wardens_mod.get_store().load_report("pvenodeone")
    assert stored is not None
    assert stored["lxc"][0]["vmid"] == 100
    assert ssh.password is None


def test_collect_unknown_node_raises(data_dir: Path) -> None:
    ssh = FakeSSH(host="")
    with pytest.raises(BridgeError, match="not enrolled"):
        collect_node(
            "missing",
            inventory=NodeInventory(data_dir),
            keys_dir=data_dir / "ssh",
            transport=ssh,
        )


def test_collect_rejects_non_json_stdout(data_dir: Path) -> None:
    ssh = FakeSSH(host="")
    ssh.exec_results = {
               "/opt/wardens/bin/wardens-collector": (0, "not-json\n", ""),
               "collect": (0, "not-json\n", ""),
           }
    with pytest.raises(BridgeError, match="JSON"):
        collect_node(
            "pvenodeone",
            inventory=NodeInventory(data_dir),
            keys_dir=data_dir / "ssh",
            transport=ssh,
        )
