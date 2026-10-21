"""Wardens registration and collector report API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import wardens as wardens_mod


@pytest.fixture()
def wardens_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data = tmp_path / "wardens-data"
    data.mkdir()
    monkeypatch.setenv("WARDENS_DATA_DIR", str(data))
    wardens_mod.reset_store_for_tests()
    yield data
    wardens_mod.reset_store_for_tests()


@pytest.fixture()
def client(wardens_data_dir: Path) -> TestClient:
    with TestClient(app) as c:
        yield c


def _sample_caps(node: str = "pvenodeone") -> dict:
    return {
        "node": node,
        "warden_version": "0.2.0",
        "collector_caps": ["lxc:full", "permissions:audit"],
        "runner_allowlist": [],
        "seccomp_profile": "none",
        "resource_limits": {"max_mem_mb": 256},
    }


def _sample_report(node: str = "pvenodeone") -> dict:
    return {
        "node": node,
        "warden_version": "0.2.0",
        "lxc": [
            {
                "vmid": 106,
                "hostname": "clustermcp",
                "rootfs": "local-lvm:vm-106-disk-0",
                "unprivileged": True,
                "status": "unknown",
            }
        ],
        "permission": {
            "target_path": "/etc/pve/lxc",
            "effective_uid": "0",
            "effective_gid": "0",
            "readable": True,
            "writable": True,
            "executable": True,
            "capabilities": "mode=755",
            "mapping_note": "basic stat + access check",
        },
    }


def test_register_warden_and_list_nodes(client: TestClient) -> None:
    r = client.post("/wardens/register", json=_sample_caps())
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["registered"] == "pvenodeone"

    listed = client.get("/wardens/nodes")
    assert listed.status_code == 200
    data = listed.json()["data"]
    assert "pvenodeone" in data["nodes"]
    assert data["nodes"]["pvenodeone"]["warden_version"] == "0.2.0"


def test_get_node_capabilities(client: TestClient) -> None:
    client.post("/wardens/register", json=_sample_caps("pvenodetwo"))
    r = client.get("/wardens/nodes/pvenodetwo/capabilities")
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert r.json()["data"]["collector_caps"] == ["lxc:full", "permissions:audit"]


def test_get_unknown_node_capabilities(client: TestClient) -> None:
    r = client.get("/wardens/nodes/missing/capabilities")
    assert r.status_code == 200
    assert r.json()["success"] is False
    assert "not registered" in r.json()["error"].lower()


def test_global_capabilities_union(client: TestClient) -> None:
    client.post(
        "/wardens/register",
        json={**_sample_caps("a"), "collector_caps": ["lxc:full"], "runner_allowlist": ["logs:collect"]},
    )
    client.post(
        "/wardens/register",
        json={**_sample_caps("b"), "collector_caps": ["permissions:audit"], "runner_allowlist": []},
    )
    r = client.get("/wardens/capabilities")
    assert r.status_code == 200
    caps = set(r.json()["data"]["all_capabilities"])
    assert caps == {"lxc:full", "permissions:audit", "logs:collect"}


def test_collector_report_roundtrip_and_persist(client: TestClient, wardens_data_dir: Path) -> None:
    report = _sample_report()
    r = client.post("/wardens/collector/report", json=report)
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert r.json()["data"]["stored"] == "pvenodeone"

    got = client.get("/wardens/nodes/pvenodeone/report")
    assert got.status_code == 200
    assert got.json()["success"] is True
    assert got.json()["data"]["node"] == "pvenodeone"
    assert got.json()["data"]["lxc"][0]["vmid"] == 106

    on_disk = wardens_data_dir / "reports" / "pvenodeone.json"
    assert on_disk.is_file()
    saved = json.loads(on_disk.read_text())
    assert saved["node"] == "pvenodeone"


def test_collector_report_missing_node_rejected(client: TestClient) -> None:
    r = client.post("/wardens/collector/report", json={"lxc": []})
    assert r.status_code == 422


def test_get_unknown_report(client: TestClient) -> None:
    r = client.get("/wardens/nodes/ghost/report")
    assert r.status_code == 200
    assert r.json()["success"] is False


def test_list_reports(client: TestClient) -> None:
    client.post("/wardens/collector/report", json=_sample_report("n1"))
    client.post("/wardens/collector/report", json=_sample_report("n2"))
    r = client.get("/wardens/reports")
    assert r.status_code == 200
    nodes = r.json()["data"]["nodes"]
    assert set(nodes) == {"n1", "n2"}
