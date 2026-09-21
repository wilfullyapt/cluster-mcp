"""Application configuration."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mcp_repo_root: Path = Path(os.getenv("MCP_REPO_ROOT", ".")).resolve()
    last_known_good_file: Path = mcp_repo_root / ".last_known_good"
    mcp_version: str = os.getenv("MCP_VERSION", "0.6.0")
    ceph_conffile: Path = Path(os.getenv("CEPH_CONFFILE", "/etc/ceph/ceph.conf"))

    class Config:
        env_file = ".env"


settings = Settings()
