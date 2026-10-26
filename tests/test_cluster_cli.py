"""CLI entry point tests for `cluster setup|nodes|collect`."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import cluster_cli
from services.node_inventory import NodeInventory, NodeRecord, reset_inventory_for_tests
from services.warden_setup import SetupResult


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "wardens-data"
    d.mkdir()
    monkeypatch.setenv("WARDENS_DATA_DIR", str(d))
    reset_inventory_for_tests()
    yield d
    reset_inventory_for_tests()


def test_cluster_setup_cli_password_stdin(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fake_result = SetupResult(
        success=True,
        node="pvenodeone",
        host="192.168.0.10",
        collector_path="/opt/wardens/bin/wardens-collector",
        key_name="warden-pvenodeone",
        message="ok",
    )
    args = SimpleNamespace(
        ip="192.168.0.10",
        user="root",
        port=22,
        node=None,
        password_stdin=True,
        no_collect=True,
    )
    with (
        patch("services.warden_setup.setup_node", return_value=fake_result) as m,
        patch("services.ssh_transport.ParamikoSSH") as ssh_cls,
        patch("sys.stdin") as stdin,
    ):
        stdin.readline.return_value = "ephemeral-secret\n"
        ssh_inst = MagicMock()
        ssh_cls.return_value = ssh_inst
        rc = cluster_cli.cmd_setup(args)
        assert rc == 0
        req = m.call_args.args[0]
        assert req.host == "192.168.0.10"
        assert req.password == "ephemeral-secret"
        ssh_inst.close.assert_called()
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["node"] == "pvenodeone"


def test_cluster_nodes_cli(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    inv = NodeInventory(data_dir)
    inv.save(
        NodeRecord(
            node="pvenodeone",
            host="192.168.0.10",
            key_name="warden-pvenodeone",
        )
    )
    rc = cluster_cli.main(["nodes"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["nodes"][0]["node"] == "pvenodeone"
