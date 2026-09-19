"""Admin / self-maintenance router for the Proxmox MCP.

Thin HTTP layer that delegates to UpdateOrchestrator.
"""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from models import ActionResponse
from security import get_api_key
from services.update_orchestrator import UpdateOrchestrator

router = APIRouter(prefix="/admin", tags=["Admin / Self-Maintenance"])

orchestrator = UpdateOrchestrator()


class UpdateRequest(BaseModel):
    ref: str = Field(default="origin/main")
    force: bool = Field(default=False)


@router.post("/update", response_model=ActionResponse)
def trigger_update(
    req: UpdateRequest,
    api_key: str | None = Depends(get_api_key) if os.getenv("MCP_API_KEY") else None,
):
    if os.getenv("MCP_API_KEY") and not api_key:
        raise HTTPException(status_code=401, detail="Valid X-API-Key required")

    result = orchestrator.perform_update(req.ref, req.force)

    # Restart service on success (non-blocking)
    if result.get("success"):
        import subprocess
        subprocess.Popen(
            ["sudo", "systemctl", "restart", "proxmox-mcp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        result["message"] = result.get("message", "") + " Service is restarting."

    return ActionResponse(success=result.get("success", False), data=result)


@router.get("/update/status", response_model=ActionResponse)
def update_status():
    last_good = ""
    if orchestrator.repo_root:
        last_good_file = Path(orchestrator.repo_root) / ".last-known-good"
        if last_good_file.exists():
            last_good = last_good_file.read_text().strip()

    return ActionResponse(
        success=True,
        data={
            "version": os.getenv("MCP_VERSION", "unknown"),
            "repo_root": str(orchestrator.repo_root),
            "last_known_good": last_good,
        },
    )
