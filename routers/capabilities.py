"""Capabilities & privilege detection — honest plane status when PVE is blind."""

from __future__ import annotations

from fastapi import APIRouter

from logging_config import get_logger
from models import ActionResponse
from pve_client import classify_pve_error, get_pve_host, pve_get, token_configured

router = APIRouter(prefix="/capabilities", tags=["Capabilities"])
logger = get_logger()


def _empty_features() -> dict[str, bool]:
    return {
        "read_audit": False,
        "vm_power": False,
        "vm_allocate": False,
        "ct_create": False,
        "storage": False,
        "ceph_full": False,
        "ceph_read": False,
        "ceph_write": False,
    }


def get_token_permissions() -> dict:
    """Detect effective permissions for the configured token."""
    if not token_configured():
        return {
            "error": "PVE_TOKEN_ID/PVE_TOKEN_SECRET not configured",
            "status": "token_missing",
            "raw": {},
            "privileges": [],
        }

    data, err = pve_get("/access/permissions")
    if err:
        status = classify_pve_error(err)
        logger.warning("Failed to get token permissions: %s (%s)", err, status)
        return {
            "error": err,
            "status": status,
            "raw": {},
            "privileges": [],
        }

    flat_privs: set[str] = set()
    raw = data if isinstance(data, dict) else {}
    for _path, privs in raw.items():
        if isinstance(privs, dict):
            flat_privs.update(str(k) for k in privs.keys())
        elif isinstance(privs, list):
            flat_privs.update(str(p) for p in privs)

    # Token present and API answered, but empty ACL → no_privs
    status = "ok" if flat_privs else "no_privs"
    return {"raw": raw, "privileges": sorted(flat_privs), "status": status, "error": None}


@router.get("", response_model=ActionResponse)
def get_capabilities():
    """Return detected token privileges, plane status, and enabled feature set."""
    perms = get_token_permissions()
    priv_list = list(perms.get("privileges") or [])
    plane_status = perms.get("status") or "unknown"

    if plane_status in ("token_missing", "token_broken", "pve_unreachable", "pve_error"):
        enabled = _empty_features()
        reason = {
            "token_missing": "PVE API token not configured on MCP",
            "token_broken": "PVE API token rejected (auth/ACL)",
            "pve_unreachable": "PVE host unreachable (DNS/network/timeout)",
            "pve_error": "PVE API error while reading permissions",
        }.get(str(plane_status), "PVE plane unavailable")
    elif plane_status == "no_privs":
        enabled = _empty_features()
        reason = "Token authenticated but returned no privileges"
    else:
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
        reason = None

    return ActionResponse(
        success=True,
        data={
            "permissions": perms,
            "enabled_features": enabled,
            "plane": {
                "pve_host": get_pve_host(),
                "status": plane_status,
                "token_configured": token_configured(),
                "reason": reason,
            },
        },
    )
