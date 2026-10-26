"""Fleet sync — one control-plane action: build bridge, push all nodes, optional collect."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from routers import wardens as wardens_mod
from services.node_inventory import NodeInventory, NodeRecord, reset_inventory_for_tests
from services.warden_fleet import FleetSyncError, fleet_sync
from tests.test_warden_setup import FakeSSH


@pytest.fixture()
def fleet_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "wardens-data"
    d.mkdir()
    monkeypatch.setenv("WARDENS_DATA_DIR", str(d))
    reset_inventory_for_tests()
    wardens_mod.reset_store_for_tests()

    bin_dir = tmp_path / "build"
    bin_dir.mkdir()
    collector = bin_dir / "collector"
    collector.write_bytes(b"\x7fELFfleet-bridge")
    monkeypatch.setenv("WARDENS_COLLECTOR_BIN", str(collector))

    inv = NodeInventory(d)
    keys = d / "ssh"
    keys.mkdir()
    for name, host in (("pvenodeone", "10.0.0.1"), ("pvenodetwo", "10.0.0.2")):
        inv.save(
            NodeRecord(
                node=name,
                host=host,
                key_name=f"warden-{name}",
                collector_path="/opt/wardens/bin/wardens-collector",
                warden_version="0.3.0",
            )
        )
        (keys / f"warden-{name}").write_text("fake-key\n")

    yield d
    reset_inventory_for_tests()
    wardens_mod.reset_store_for_tests()


def test_fleet_sync_updates_all_and_collects(fleet_dir: Path) -> None:
    report = {
        "node": "PLACEHOLDER",
        "warden_version": "0.4.0",
        "lxc": [],
        "permission": {
            "target_path": "/etc/pve/lxc",
            "effective_uid": "0",
            "effective_gid": "0",
            "readable": True,
            "writable": True,
            "executable": True,
            "capabilities": "",
            "mapping_note": "ok",
        },
        "host": {"loadavg_1": 0.1, "mem_total_bytes": 1000, "mem_available_bytes": 500},
    }

    transports: list[FakeSSH] = []

    def factory() -> FakeSSH:
        ssh = FakeSSH(host="")
        ssh.exec_results = {
            "install -d": (0, "", ""),
            "test -x /opt/wardens/bin/wardens-collector": (0, "", ""),
            "install-binary": (0, '{"ok":true}\n', ""),
            "collect": (
                0,
                json.dumps({**report, "node": "x"}) + "\n",
                "",
            ),
            "/opt/wardens/bin/wardens-collector": (
                0,
                json.dumps({**report, "node": "x"}) + "\n",
                "",
            ),
        }
        transports.append(ssh)
        return ssh

    builds: list[str] = []

    def fake_build() -> Path:
        builds.append("ok")
        p = Path(__import__("os").environ["WARDENS_COLLECTOR_BIN"])
        p.write_bytes(b"\x7fELFfleet-bridge-v2")
        return p

    result = fleet_sync(
        inventory=NodeInventory(fleet_dir),
        keys_dir=fleet_dir / "ssh",
        transport_factory=factory,
        build_fn=fake_build,
        do_build=True,
        do_update=True,
        do_collect=True,
        version="0.4.0",
    )

    assert result.success is True
    assert builds == ["ok"]
    assert len(result.nodes) == 2
    names = {n.node for n in result.nodes}
    assert names == {"pvenodeone", "pvenodetwo"}
    assert all(n.update_ok for n in result.nodes)
    assert all(n.collect_ok for n in result.nodes)
    assert all(n.error is None for n in result.nodes)

    inv = NodeInventory(fleet_dir)
    assert inv.get("pvenodeone").warden_version == "0.4.0"
    assert wardens_mod.get_store().load_report("pvenodeone") is not None
    assert wardens_mod.get_store().load_report("pvenodetwo") is not None


def test_fleet_sync_partial_failure_still_reports(fleet_dir: Path) -> None:
    call_n = {"i": 0}

    def factory() -> FakeSSH:
        ssh = FakeSSH(host="")
        call_n["i"] += 1
        if call_n["i"] == 1:
            # first node update fails
            ssh.exec_results = {
                "install-binary": (1, "", "missing"),
            }
        else:
            ssh.exec_results = {
                "install-binary": (0, '{"ok":true}\n', ""),
                "collect": (
                    0,
                    json.dumps(
                        {
                            "node": "pvenodetwo",
                            "warden_version": "0.4.0",
                            "lxc": [],
                        }
                    )
                    + "\n",
                    "",
                ),
            }
        return ssh

    result = fleet_sync(
        inventory=NodeInventory(fleet_dir),
        keys_dir=fleet_dir / "ssh",
        transport_factory=factory,
        build_fn=lambda: Path(__import__("os").environ["WARDENS_COLLECTOR_BIN"]),
        do_build=True,
        do_update=True,
        do_collect=True,
        version="0.4.0",
    )

    assert result.success is False
    assert any(not n.update_ok for n in result.nodes)
    assert any(n.update_ok for n in result.nodes)


def test_fleet_sync_no_nodes_raises(fleet_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("WARDENS_DATA_DIR", str(empty))
    reset_inventory_for_tests()
    with pytest.raises(FleetSyncError, match="no enrolled"):
        fleet_sync(
            inventory=NodeInventory(empty),
            keys_dir=empty / "ssh",
            transport_factory=FakeSSH,
            build_fn=lambda: Path("x"),
            do_build=False,
            do_update=True,
            do_collect=False,
        )
