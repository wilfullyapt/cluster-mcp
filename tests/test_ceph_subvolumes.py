"""CephFS subvolume list/info API tests — no silent fixture invention."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from clients.ceph_client import PveApiCephAdapter
from exceptions import CephConnectionError
from main import app
from services.ceph_service import CephService


class _FakeAdapter(PveApiCephAdapter):
    def __init__(self, mapping: dict[str, object]):
        # Skip real session init
        self.sess = MagicMock()
        self.pve_host = "https://pve-test:8006"
        self.timeout = 1.0
        self._mapping = mapping
        self.calls: list[str] = []

    def _get(self, path: str):
        self.calls.append(path)
        if path in self._mapping:
            val = self._mapping[path]
            if isinstance(val, Exception):
                raise val
            return val
        raise CephConnectionError(f"PVE API call failed: {path} -> 404")


def test_list_subvolumes_from_pve_payload():
    adapter = _FakeAdapter(
        {
            "/cluster/ceph/fs": [{"name": "cephfs", "status": "active"}],
            "/cluster/ceph/fs/cephfs/subvolume": [
                {"name": "immich", "path": "/volumes/_nogroup/immich/x", "quota": 1000, "used": 100},
                {"name": "syncthing", "path": "/volumes/_nogroup/syncthing/y"},
            ],
        }
    )
    result = adapter.list_subvolumes()
    assert result["fs"] == "cephfs"
    assert result["count"] == 2
    names = {s["name"] for s in result["subvolumes"]}
    assert names == {"immich", "syncthing"}
    immich = next(s for s in result["subvolumes"] if s["name"] == "immich")
    assert immich["path"]
    assert immich["quota_bytes"] == 1000


def test_list_subvolumes_empty_when_all_paths_fail():
    adapter = _FakeAdapter({"/cluster/ceph/fs": [{"name": "cephfs"}]})
    result = adapter.list_subvolumes()
    assert result["subvolumes"] == []
    assert result["count"] == 0
    assert result["probe_errors"]  # honest — not silent fixture data


def test_get_subvolume_info():
    adapter = _FakeAdapter(
        {
            "/cluster/ceph/fs": [{"name": "cephfs"}],
            "/cluster/ceph/fs/cephfs/subvolume/keep": {
                "name": "keep",
                "path": "/volumes/_nogroup/keep/uuid",
                "quota_bytes": 999,
                "used_bytes": 10,
            },
        }
    )
    info = adapter.get_subvolume("keep")
    assert info["name"] == "keep"
    assert info["path"]
    assert info["quota_bytes"] == 999


def test_list_cephfs_storages():
    adapter = _FakeAdapter(
        {
            "/storage": [
                {"storage": "cephfs", "type": "cephfs"},
                {"storage": "cephfs-immich", "type": "cephfs"},
                {"storage": "local-lvm", "type": "lvmthin"},
            ],
            "/cluster/resources?type=storage": [
                {"storage": "cephfs-syncthing", "plugintype": "cephfs", "node": "pvenodetwo", "status": "available"},
            ],
        }
    )
    result = adapter.list_cephfs_storages()
    ids = {s["storage"] for s in result["storages"]}
    assert "cephfs" in ids
    assert "cephfs-immich" in ids
    assert "cephfs-syncthing" in ids
    assert "local-lvm" not in ids


def test_service_list_subvolumes_delegates():
    client = MagicMock()
    client.list_subvolumes.return_value = {"fs": "cephfs", "subvolumes": [], "count": 0}
    svc = CephService(client=client)
    out = svc.list_subvolumes(fs_name="cephfs")
    assert out["count"] == 0
    client.list_subvolumes.assert_called_once()


def test_http_fs_subvolumes_endpoint():
    mock_svc = MagicMock()
    mock_svc.list_subvolumes.return_value = {
        "fs": "cephfs",
        "subvolumes": [{"name": "keep", "path": "/keep", "quota_bytes": None, "used_bytes": None}],
        "count": 1,
        "available": True,
    }
    from routers.ceph import get_ceph_service

    app.dependency_overrides[get_ceph_service] = lambda: mock_svc
    try:
        with TestClient(app) as client:
            r = client.get("/ceph/fs-subvolumes")
            assert r.status_code == 200
            body = r.json()
            assert body["success"] is True
            assert body["data"]["count"] == 1
    finally:
        app.dependency_overrides.pop(get_ceph_service, None)


def test_http_fs_subvolumes_soft_fail():
    mock_svc = MagicMock()
    mock_svc.list_subvolumes.side_effect = CephConnectionError("PVE down")
    from routers.ceph import get_ceph_service

    app.dependency_overrides[get_ceph_service] = lambda: mock_svc
    try:
        with TestClient(app) as client:
            r = client.get("/ceph/fs-subvolumes")
            assert r.status_code == 200
            body = r.json()
            assert body["success"] is False
            assert body["data"]["available"] is False
    finally:
        app.dependency_overrides.pop(get_ceph_service, None)


def test_http_storage_endpoint():
    mock_svc = MagicMock()
    mock_svc.list_cephfs_storages.return_value = {
        "storages": [{"storage": "cephfs", "type": "cephfs"}],
        "count": 1,
        "available": True,
    }
    from routers.ceph import get_ceph_service

    app.dependency_overrides[get_ceph_service] = lambda: mock_svc
    try:
        with TestClient(app) as client:
            r = client.get("/ceph/storage")
            assert r.status_code == 200
            assert r.json()["data"]["count"] == 1
    finally:
        app.dependency_overrides.pop(get_ceph_service, None)
