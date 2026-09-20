"""Admin / self-maintenance router for the Proxmox MCP.

Thin HTTP layer that delegates to UpdateOrchestrator.
"""

from fastapi import APIRouter, Depends

from services.update_orchestrator import UpdateOrchestrator


def get_update_orchestrator() -> UpdateOrchestrator:
    return UpdateOrchestrator()


router = APIRouter(prefix="/admin", tags=["Admin / Self-Maintenance"])


@router.post("/update")
def trigger_update(
    ref: str,
    force: bool = False,
    orchestrator: UpdateOrchestrator = Depends(get_update_orchestrator),
):
    return orchestrator.perform_update(ref, force=force)
