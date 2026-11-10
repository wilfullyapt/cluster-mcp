"""Cluster and node status router — soft-fail when PVE plane is down."""

from __future__ import annotations

from fastapi import APIRouter

from logging_config import get_logger
from models import ActionResponse
from pve_client import classify_pve_error, get_pve_host, pve_get

router = APIRouter(prefix="/cluster", tags=["Cluster"])
logger = get_logger()


def _soft(path: str, label: str) -> ActionResponse:
    data, err = pve_get(path)
    if err:
        logger.warning("cluster.%s failed: %s", label, err)
        return ActionResponse(
            success=False,
            error=err,
            data={
                "available": False,
                "plane": "pve",
                "pve_host": get_pve_host(),
                "status": classify_pve_error(err),
                "path": path,
                "label": label,
            },
        )
    return ActionResponse(success=True, data=data)


@router.get("/status", response_model=ActionResponse)
def cluster_status():
    return _soft("/cluster/status", "status")


@router.get("/nodes", response_model=ActionResponse)
def list_nodes():
    return _soft("/nodes", "nodes")


@router.get("/resources", response_model=ActionResponse)
def cluster_resources(type: str | None = None):
    path = "/cluster/resources"
    if type:
        path = f"{path}?type={type}"
    return _soft(path, "resources")
