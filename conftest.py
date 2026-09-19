import os

import pytest

from clients.ceph import CephClient


@pytest.fixture(autouse=True, scope="session")
def set_dummy_pve_credentials():
    """Ensure PVE client doesn't crash during test collection."""
    os.environ.setdefault("PVE_TOKEN_ID", "test-token")
    os.environ.setdefault("PVE_TOKEN_SECRET", "test-secret")
    os.environ.setdefault("PVE_HOST", "https://pve-01:8006")
    yield


@pytest.fixture
def ceph_client_mock():
    """Provide a CephClient with explicit 'mock' backend for unit tests."""
    client = CephClient(config={}, backend=None)  # Will use no real backends
    yield client
    client.close()
