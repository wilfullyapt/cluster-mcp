"""Ceph status router.

Uses CephService (which wraps CephClient) for richer data.
Soft-fails with JSON when PVE/Ceph plane is down — never kills the worker.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from exceptions import CephConnectionError, CephPermissionError
from logging_config import get_logger
from models import ActionResponse
from pve_client import classify_pve_error, get_pve_host
from services.ceph_service import CephService

router = APIRouter(prefix="/ceph", tags=["Ceph"])
logger = get_logger()


def get_ceph_service() -> CephService:
    return CephService()


def _soft_fail(exc: Exception, label: str) -> dict[str, Any]:
    err = f"{type(exc).__name__}: {exc}"
    status = classify_pve_error(err)
    logger.warning("ceph.%s failed: %s", label, err)
    return {
        "success": False,
        "error": err,
        "data": {
            "available": False,
            "plane": "ceph",
            "label": label,
            "status": status,
            "pve_host": get_pve_host(),
        },
    }


@router.get("/health")
def ceph_health(service: CephService = Depends(get_ceph_service)):
    try:
        return {"success": True, "data": service.get_health()}
    except (CephConnectionError, CephPermissionError, Exception) as exc:  # noqa: BLE001
        return _soft_fail(exc, "health")


@router.get("/status")
def ceph_status(service: CephService = Depends(get_ceph_service)):
    try:
        return {"success": True, "data": service.get_status()}
    except (CephConnectionError, CephPermissionError, Exception) as exc:  # noqa: BLE001
        return _soft_fail(exc, "status")


@router.get("/osds")
def ceph_osds(service: CephService = Depends(get_ceph_service)):
    try:
        return {"success": True, "data": service.get_osds()}
    except (CephConnectionError, CephPermissionError, Exception) as exc:  # noqa: BLE001
        return _soft_fail(exc, "osds")


@router.get("/fs")
def ceph_fs(service: CephService = Depends(get_ceph_service)):
    try:
        return {"success": True, "data": service.get_fs()}
    except (CephConnectionError, CephPermissionError, Exception) as exc:  # noqa: BLE001
        return _soft_fail(exc, "fs")


@router.get("/fs-subvolumes", response_model=ActionResponse)
def ceph_fs_subvolumes(
    fs: str | None = Query(None, description="CephFS name (default: first FS or 'cephfs')"),
    group: str | None = Query(None, description="Optional subvolume group filter"),
    service: CephService = Depends(get_ceph_service),
):
    """List CephFS subvolumes (path/quota/used when PVE exposes them)."""
    try:
        data = service.list_subvolumes(fs_name=fs, group=group)
        return ActionResponse(success=True, data=data)
    except (CephConnectionError, CephPermissionError, Exception) as exc:  # noqa: BLE001
        body = _soft_fail(exc, "fs-subvolumes")
        return ActionResponse(success=False, error=body["error"], data=body["data"])


@router.get("/fs-subvolumes/{name}", response_model=ActionResponse)
def ceph_fs_subvolume_info(
    name: str,
    fs: str | None = Query(None, description="CephFS name"),
    group: str | None = Query(None, description="Subvolume group"),
    service: CephService = Depends(get_ceph_service),
):
    """Info for one CephFS subvolume (path, quota, used if available)."""
    try:
        data = service.get_subvolume(name=name, fs_name=fs, group=group)
        return ActionResponse(success=True, data=data)
    except (CephConnectionError, CephPermissionError, Exception) as exc:  # noqa: BLE001
        body = _soft_fail(exc, "fs-subvolume-info")
        return ActionResponse(success=False, error=body["error"], data=body["data"])


@router.get("/storage", response_model=ActionResponse)
def ceph_storage_ids(service: CephService = Depends(get_ceph_service)):
    """Surface PVE storage IDs that look like CephFS (cephfs, cephfs-immich, …)."""
    try:
        data = service.list_cephfs_storages()
        return ActionResponse(success=True, data=data)
    except (CephConnectionError, CephPermissionError, Exception) as exc:  # noqa: BLE001
        body = _soft_fail(exc, "storage")
        return ActionResponse(success=False, error=body["error"], data=body["data"])
