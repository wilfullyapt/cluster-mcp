"""Ceph status router.

Uses CephService (which wraps CephClient) for richer data.
"""

from fastapi import APIRouter, Depends, HTTPException

from exceptions import CephConnectionError
from services.ceph_service import CephService


def get_ceph_service() -> CephService:
    return CephService()


router = APIRouter(prefix="/ceph", tags=["Ceph"])


@router.get("/health")
def ceph_health(service: CephService = Depends(get_ceph_service)):
    try:
        return {"success": True, "data": service.get_health()}
    except CephConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/status")
def ceph_status(service: CephService = Depends(get_ceph_service)):
    try:
        return {"success": True, "data": service.get_status()}
    except CephConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/osds")
def ceph_osds(service: CephService = Depends(get_ceph_service)):
    try:
        return {"success": True, "data": service.get_osds()}
    except CephConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/fs")
def ceph_fs(service: CephService = Depends(get_ceph_service)):
    try:
        return {"success": True, "data": service.get_fs()}
    except CephConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
