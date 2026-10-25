"""Node inventory — enrolled Wardens nodes; never stores passwords."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.node_inventory import NodeInventory, NodeRecord, reset_inventory_for_tests


@pytest.fixture()
def inv_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data = tmp_path / "wardens-data"
    data.mkdir()
    monkeypatch.setenv("WARDENS_DATA_DIR", str(data))
    reset_inventory_for_tests()
    yield data
    reset_inventory_for_tests()


def test_save_and_load_node_without_password_field(inv_dir: Path) -> None:
    inv = NodeInventory(inv_dir)
    rec = NodeRecord(
        node="pvenodeone",
        host="192.168.0.10",
        ssh_user="root",
        ssh_port=22,
        auth_method="ssh_key",
        key_name="warden-pvenodeone",
        collector_path="/opt/wardens/bin/wardens-collector",
        warden_version="0.3.0",
        collector_caps=["lxc:full", "permissions:audit"],
    )
    inv.save(rec)

    loaded = inv.get("pvenodeone")
    assert loaded is not None
    assert loaded.host == "192.168.0.10"
    assert loaded.auth_method == "ssh_key"
    dump = json.loads((inv_dir / "nodes" / "pvenodeone.json").read_text())
    assert "password" not in dump
    assert "password" not in json.dumps(dump).lower() or "password" not in dump


def test_list_nodes(inv_dir: Path) -> None:
    inv = NodeInventory(inv_dir)
    inv.save(
        NodeRecord(
            node="a",
            host="10.0.0.1",
            ssh_user="root",
            ssh_port=22,
            auth_method="ssh_key",
            key_name="k-a",
        )
    )
    inv.save(
        NodeRecord(
            node="b",
            host="10.0.0.2",
            ssh_user="root",
            ssh_port=22,
            auth_method="ssh_key",
            key_name="k-b",
        )
    )
    names = {n.node for n in inv.list_nodes()}
    assert names == {"a", "b"}


def test_rejects_invalid_node_name(inv_dir: Path) -> None:
    inv = NodeInventory(inv_dir)
    with pytest.raises(ValueError):
        inv.save(
            NodeRecord(
                node="../etc",
                host="10.0.0.1",
                ssh_user="root",
                ssh_port=22,
                auth_method="ssh_key",
                key_name="x",
            )
        )
