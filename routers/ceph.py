"""Ceph status router.

Uses CephService (which wraps CephClient) for richer data.
"""

from fastapi import APIRouter, HTTPException

from models import ActionResponse
from services.ceph_service import ceph_service

router = APIRouter(prefix="/ceph", tags=["Ceph"])


@router.get("/status", response_model=ActionResponse)
def ceph_status():
    try:
        data = ceph_service.get_health()
        return ActionResponse(success=True, data=data)
    except Exception:
        from logging_config import get_logger
        logger = get_logger()
        logger.exception("Failed to get Ceph status")
        raise HTTPException(500, detail="Failed to retrieve Ceph status")


@router.get("/health", response_model=ActionResponse)
def ceph_health():
    try:
        data = ceph_service.get_health()
        return ActionResponse(success=True, data=data)
    except Exception:
        from logging_config import get_logger
        logger = get_logger()
        logger.exception("Ceph health check failed")
        raise HTTPException(500, detail="Ceph health check failed")


@router.get("/osds", response_model=ActionResponse)
def ceph_osds():
    try:
        data = ceph_service.get_osd_status()
        return ActionResponse(success=True, data=data)
    except Exception:
        from logging_config import get_logger
        logger = get_logger()
        logger.exception("Failed to get Ceph OSDs")
        raise HTTPException(500, detail="Failed to retrieve Ceph OSDs")


@router.get("/pools", response_model=ActionResponse)
def ceph_pools():
    try:
        data = ceph_service.get_pool_stats()
        return ActionResponse(success=True, data=data)
    except Exception:
        from logging_config import get_logger
        logger = get_logger()
        logger.exception("Failed to get Ceph pool stats")
        raise HTTPException(500, detail="Failed to retrieve Ceph pool stats")


@router.get("/fs", response_model=ActionResponse)
def ceph_fs():
    try:
        data = ceph_service.get_cephfs_usage()
        return ActionResponse(success=True, data=data)
    except Exception:
        from logging_config import get_logger
        logger = get_logger()
        logger.exception("Failed to get CephFS usage")
        raise HTTPException(500, detail="Failed to retrieve CephFS usage")
