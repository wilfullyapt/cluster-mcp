"""Application configuration."""

import os
from pathlib import Path


class Settings:
    def __init__(self):
        self.mcp_repo_root = Path(os.getenv("MCP_REPO_ROOT", ".")).resolve()
        self.last_known_good_file = self.mcp_repo_root / ".last_known_good"

settings = Settings()
