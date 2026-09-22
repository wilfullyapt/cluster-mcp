"""Capabilities & privilege detection router."""

import os

from fastapi import APIRouter

from models import ActionResponse
from pve_client import get_session

router = APIRouter(prefix="/capabilities", tags=["Capabilities"])


def get_token_permissions():
    """Detect effective permissions for the configured token."""
    try:
        sess = get_session()
        r = sess.get(f"{os.getenv('PVE_HOST', 'https://pve-01:8006')}/api2/json/access/permissions")
        r.raise_for_status()
        data = r.json().get("data", {})
        flat_privs = set()
        for path, privs in data.items():
            if isinstance(privs, dict):
                flat_privs.update(privs.keys())
            elif isinstance(privs, list):
                flat_privs.update(privs)
        return {"raw": data, "privileges": list(flat_privs)}
    except Exception:
        from logging_config import get_logger
        logger = get_logger()
        logger.exception("Failed to get token permissions")
        return {"error": "Failed to retrieve permissions"}


@router.get("", response_model=ActionResponse)
def get_capabilities():
    """Return detected token privileges and enabled feature set."""
    perms = get_token_permissions()
    priv_list = perms.get("privileges", [])
    enabled = {
        "read_audit": any("Audit" in p for p in priv_list),
        "vm_power": "VM.PowerMgmt" in priv_list,
        "vm_allocate": "VM.Allocate" in priv_list,
        "ct_create": "VM.Allocate" in priv_list,
        "storage": any("Datastore" in p for p in priv_list),
        "ceph_full": "Ceph.Audit" in priv_list and "Sys.Audit" in priv_list,
        "ceph_read": "Ceph.Audit" in priv_list or "Sys.Audit" in priv_list,
        "ceph_write": any(p in priv_list for p in ["Ceph.Manage", "Sys.Modify"]),
    }
    return ActionResponse(success=True, data={
        "permissions": perms,
        "enabled_features": enabled
    })
