"""Wardens registration and capabilities router.

MCP side for discovering what each node Warden can see and do.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any

from logging_config import get_logger
from models import ActionResponse

router = APIRouter(prefix="/wardens", tags=["Wardens"])

logger = get_logger()

# In-memory store for demo (replace with DB later)
node_capabilities: Dict[str, Dict[str, Any]] = {}


class WardenCapabilities(BaseModel):
    node: str
    warden_version: str
    collector_caps: List[str]
    runner_allowlist: List[str]
    seccomp_profile: str
    resource_limits: Dict[str, Any]


@router.post("/register", response_model=ActionResponse)
def register_warden(caps: WardenCapabilities):
    """Register or update a Warden node's capabilities."""
    node_capabilities[caps.node] = caps.model_dump()
    logger.info(f"Warden registered: {caps.node} v{caps.warden_version}")
    return ActionResponse(success=True, data={"registered": caps.node})


@router.get("/nodes", response_model=ActionResponse)
def list_nodes():
    """List all registered Wardens and their high-level caps."""
    return ActionResponse(success=True, data=list(node_capabilities.keys()))


@router.get("/nodes/{node}/capabilities", response_model=ActionResponse)
def get_node_capabilities(node: str):
    """Return full capabilities report for a specific node."""
    if node not in node_capabilities:
        return ActionResponse(success=False, error="Node not registered")
    return ActionResponse(success=True, data=node_capabilities[node])


@router.get("/capabilities", response_model=ActionResponse)
def global_capabilities():
    """Aggregate view of what capabilities exist across the cluster."""
    all_caps = set()
    for data in node_capabilities.values():
        all_caps.update(data.get("collector_caps", []))
        all_caps.update(data.get("runner_allowlist", []))
    return ActionResponse(success=True, data={"all_capabilities": list(all_caps)})

# Simple in-memory storage for collected visibility data
visibility_reports: Dict[str, Dict[str, Any]] = {}


@router.post("/collector/report", response_model=ActionResponse)
def receive_collector_report(report: dict):
    """Accept visibility data from a Warden collector."""
    node = report.get("node", "unknown")
    visibility_reports[node] = report
    logger.info(f"Received visibility report from {node}")
    return ActionResponse(success=True, data={"stored": node, "fields": list(report.keys())})
