import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def set_dummy_pve_credentials():
    """Ensure PVE client doesn't crash during test collection."""
    os.environ.setdefault("PVE_TOKEN_ID", "test-token")
    os.environ.setdefault("PVE_TOKEN_SECRET", "test-secret")
    os.environ.setdefault("PVE_HOST", "https://pve-01:8006")
    yield
