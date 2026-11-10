"""Regression: PVE plane soft-fail resilience + unified host + honest capabilities."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from main import APP_VERSION, app
from pve_client import classify_pve_error, get_pve_host
from routers.report import collect_visibility_report


def test_health_version_matches_app_constant():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["version"] == APP_VERSION
        assert body["data"]["pve_host"] == get_pve_host()


def test_classify_pve_error_dns():
    assert classify_pve_error("ConnectionError: Failed to resolve 'pve-01'") == "pve_unreachable"
    assert classify_pve_error("ConnectTimeout: timed out") == "pve_unreachable"
    assert classify_pve_error("HTTPError: 401 Unauthorized") == "token_broken"


def test_cluster_status_soft_fails_when_pve_down(monkeypatch):
    monkeypatch.setenv("PVE_HOST", "https://pve-does-not-exist.invalid:8006")

    def boom(*_a, **_k):
        return None, "ConnectionError: Failed to resolve 'pve-does-not-exist.invalid'"

    with patch("routers.cluster.pve_get", side_effect=boom):
        with TestClient(app) as client:
            r = client.get("/cluster/status")
            assert r.status_code == 200
            body = r.json()
            assert body["success"] is False
            assert body["data"]["available"] is False
            assert body["data"]["status"] == "pve_unreachable"


def test_ceph_status_soft_fails_when_service_raises():
    from routers.ceph import get_ceph_service

    inst = MagicMock()
    inst.get_status.side_effect = Exception("Name or service not known")
    app.dependency_overrides[get_ceph_service] = lambda: inst
    try:
        with TestClient(app) as client:
            r = client.get("/ceph/status")
            assert r.status_code == 200
            body = r.json()
            assert body["success"] is False
            assert body["data"]["available"] is False
    finally:
        app.dependency_overrides.pop(get_ceph_service, None)


def test_capabilities_distinguishes_unreachable(monkeypatch):
    monkeypatch.setenv("PVE_TOKEN_ID", "user@pam!tok")
    monkeypatch.setenv("PVE_TOKEN_SECRET", "secret")

    def boom(*_a, **_k):
        return None, "ConnectionError: Failed to resolve 'pve-01'"

    with patch("routers.capabilities.pve_get", side_effect=boom):
        with patch("routers.capabilities.token_configured", return_value=True):
            with TestClient(app) as client:
                r = client.get("/capabilities")
                assert r.status_code == 200
                body = r.json()
                assert body["success"] is True
                plane = body["data"]["plane"]
                assert plane["status"] == "pve_unreachable"
                assert body["data"]["enabled_features"]["ct_create"] is False
                assert plane["reason"]


def test_capabilities_token_missing(monkeypatch):
    monkeypatch.delenv("PVE_TOKEN_ID", raising=False)
    monkeypatch.delenv("PVE_TOKEN_SECRET", raising=False)
    with patch("routers.capabilities.token_configured", return_value=False):
        with TestClient(app) as client:
            r = client.get("/capabilities")
            assert r.status_code == 200
            body = r.json()
            assert body["data"]["plane"]["status"] == "token_missing"
            assert all(v is False for v in body["data"]["enabled_features"].values())


def test_visibility_collect_with_failing_pve_does_not_raise():
    def boom(path, timeout=None):
        return None, "ConnectionError: Failed to resolve 'pve-01'"

    with patch("routers.report._safe_get", side_effect=boom):
        with patch("routers.report.CephService") as svc_cls:
            inst = MagicMock()
            inst.get_status.side_effect = Exception("PVE down")
            inst.get_osds.side_effect = Exception("PVE down")
            svc_cls.return_value = inst
            report = collect_visibility_report(include_graph_data=False)
            assert report["overall"] == "down"
            assert report["probe_errors"]
            assert report["data_policy"] == "live_probes_only"
            assert any("Next:" in a for a in report.get("attention") or []) or report.get("warnings")


def test_visibility_http_soft_fail():
    with patch(
        "routers.report.collect_visibility_report",
        side_effect=RuntimeError("should be caught"),
    ):
        with TestClient(app) as client:
            r = client.get("/report/visibility")
            assert r.status_code == 200
            body = r.json()
            assert body["success"] is False
            assert body["data"]["overall"] == "down"


def test_lxc_create_soft_fails_when_pve_down():
    with patch("routers.lxc.token_configured", return_value=True):
        with patch("routers.lxc.get_session") as gs:
            sess = MagicMock()
            sess.post.side_effect = Exception("Failed to resolve 'pve-01'")
            gs.return_value = sess
            with TestClient(app) as client:
                r = client.post(
                    "/lxc/create",
                    json={
                        "node": "pvenodeone",
                        "vmid": 120,
                        "hostname": "samba",
                        "ostemplate": "local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst",
                    },
                )
                assert r.status_code == 200
                body = r.json()
                assert body["success"] is False
                assert body["data"]["available"] is False


def test_samba_share_template_docs_only():
    with TestClient(app) as client:
        r = client.get(
            "/lxc/samba-share-template",
            params={"ostemplate": "local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert "keep" in body["data"]["cephfs_mp"]
        assert any("dual-write" in x.lower() for x in body["data"]["hard_rules"])
