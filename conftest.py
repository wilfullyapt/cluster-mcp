import os
from unittest.mock import MagicMock

import pytest

from clients.ceph_client import CephClient


@pytest.fixture(autouse=True, scope="session")
def set_dummy_pve_credentials():
    """Ensure PVE client doesn't crash during test collection."""
    os.environ.setdefault("PVE_TOKEN_ID", "test-token")
    os.environ.setdefault("PVE_TOKEN_SECRET", "test-secret")
    os.environ.setdefault("PVE_HOST", "https://pve-01:8006")
    yield


@pytest.fixture
def ceph_client_mock():
    """Mock CephClient for tests that don't need real Ceph."""
    mock = MagicMock(spec=CephClient)
    mock.get_health.return_value = {"status": "HEALTH_OK"}
    mock.get_status.return_value = {"health": {"status": "HEALTH_OK"}}
    mock.get_osds.return_value = []
    mock.get_fs.return_value = {"name": "cephfs", "status": "active", "subvolumes": []}
    return mock
