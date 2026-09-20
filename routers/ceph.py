"""Ceph status router.

Uses CephService (which wraps CephClient) for richer data.
"""

from fastapi import APIRouter

from models import ActionResponse

router = APIRouter(prefix="/ceph", tags=["Ceph"])


@router.get("/status", response_model=ActionResponse)
def ceph_status():
    """Placeholder for status endpoint."""
    return {"status": "ok"}
