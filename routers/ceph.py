"""Ceph status router.

Uses CephService (which wraps CephClient) for richer data.
"""

from fastapi import APIRouter, Depends

from services.ceph_service import CephService


def get_ceph_service() -> CephService:
    return CephService()


router = APIRouter(prefix="/ceph", tags=["Ceph"])


@router.get("/health")
def ceph_health(service: CephService = Depends(get_ceph_service)):
    return service.get_health()
