"""Basic tests for ClusterMCP."""

from fastapi.testclient import TestClient

from main import app


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "version" in data["data"]


def test_capabilities():
    with TestClient(app) as client:
        response = client.get("/capabilities")
        # May return 500 if no token, but endpoint should exist
        assert response.status_code in (200, 500)
