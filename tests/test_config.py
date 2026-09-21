"""Basic tests for centralized configuration."""

from pathlib import Path

from config import Settings


def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("MCP_REPO_ROOT", raising=False)
    settings = Settings()
    assert isinstance(settings.mcp_repo_root, Path)
    assert settings.ceph_conffile.name == "ceph.conf"


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("MCP_VERSION", "1.2.3-test")
    monkeypatch.setenv("CEPH_CONFFILE", "/tmp/custom/ceph.conf")
    settings = Settings()
    assert settings.mcp_version == "1.2.3-test"
    assert str(settings.ceph_conffile) == "/tmp/custom/ceph.conf"
