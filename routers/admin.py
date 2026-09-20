"""Admin / self-maintenance router for the Proxmox MCP.

Thin HTTP layer that delegates to UpdateOrchestrator.
"""


from fastapi import APIRouter

from services.update_orchestrator import UpdateOrchestrator

router = APIRouter(prefix="/admin", tags=["Admin / Self-Maintenance"])

orchestrator = UpdateOrchestrator()
