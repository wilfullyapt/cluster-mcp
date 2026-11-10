"""Application configuration — single source for version and PVE plane defaults."""

from __future__ import annotations

import os
from functools import lru_cache
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path

from pydantic_settings import BaseSettings

# Canonical default when PVE_HOST is unset. All PVE/Ceph/report clients must use
# get_pve_host() so DNS/auth failures surface honestly instead of drifting defaults.
DEFAULT_PVE_HOST = "https://pve-01:8006"
DEFAULT_PVE_TIMEOUT_SEC = 8.0


def _version_from_pyproject(root: Path) -> str | None:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        import tomllib
    except ImportError:  # pragma: no cover — py311+
        return None
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except OSError:
        return None
    project = data.get("project") if isinstance(data, dict) else None
    if isinstance(project, dict):
        ver = project.get("version")
        if isinstance(ver, str) and ver.strip():
            return ver.strip()
    return None


def resolve_app_version(repo_root: Path | None = None) -> str:
    """Single version string for /health, OpenAPI, and ops cards.

    Preference: MCP_VERSION / CLUSTERMCP_VERSION env → installed package →
    pyproject.toml → conservative fallback.
    """
    for key in ("MCP_VERSION", "CLUSTERMCP_VERSION"):
        env_v = os.getenv(key)
        if env_v and env_v.strip():
            return env_v.strip()
    try:
        return pkg_version("clustermcp")
    except PackageNotFoundError:
        pass
    root = (repo_root or Path(os.getenv("MCP_REPO_ROOT", ".")).resolve())
    from_file = _version_from_pyproject(root)
    if from_file:
        return from_file
    return "0.9.0-dev"


def get_pve_host() -> str:
    """Unified PVE API base URL (no trailing slash)."""
    return os.getenv("PVE_HOST", DEFAULT_PVE_HOST).rstrip("/")


def get_pve_timeout() -> float:
    raw = os.getenv("PVE_TIMEOUT_SEC", str(DEFAULT_PVE_TIMEOUT_SEC))
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_PVE_TIMEOUT_SEC
    return val if val > 0 else DEFAULT_PVE_TIMEOUT_SEC


class Settings(BaseSettings):
    mcp_repo_root: Path = Path(os.getenv("MCP_REPO_ROOT", ".")).resolve()
    last_known_good_file: Path = mcp_repo_root / ".last_known_good"
    mcp_version: str = ""
    ceph_conffile: Path = Path(os.getenv("CEPH_CONFFILE", "/etc/ceph/ceph.conf"))

    model_config = {
        "env_file": ".env",
        "extra": "allow",
    }

    def model_post_init(self, __context) -> None:  # type: ignore[override]
        if not self.mcp_version:
            object.__setattr__(self, "mcp_version", resolve_app_version(self.mcp_repo_root))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
