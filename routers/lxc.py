"""LXC management router (priv-gated creation for reverse proxy etc.).

When the PVE plane is down, create/exec return honest soft-fail JSON instead of
killing the worker or pretending the CT was created.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import get_pve_timeout
from logging_config import get_logger
from models import ActionResponse, LXCCreateRequest
from pve_client import classify_pve_error, get_pve_host, get_session, token_configured

router = APIRouter(prefix="/lxc", tags=["LXC"])
logger = get_logger()


class ReverseProxyTemplate(BaseModel):
    hostname: str = "reverse-proxy"
    ostemplate: str = Field(..., description="Debian 12 standard template path")
    memory: int = 1024
    cores: int = 2
    net0: str = Field("name=eth0,bridge=vmbr0,ip=192.168.0.10/24,gw=192.168.0.1")
    rootfs: str = "local-lvm:20"
    recommended_packages: list[str] = ["caddy", "curl"]
    notes: str = "After creation: install Docker + run Gitea/Registry containers"


class SambaShareTemplate(BaseModel):
    """Guidance-only template for a Samba LXC mounting CephFS keep parent.

    Product docs / design notes — does not create production CTs.
    See Stronghold runbooks: ceph-samba-keep-immich-syncthing.md,
    unprivileged-lxc-cephfs-permission-cooperation.md.
    """

    hostname: str = "samba"
    ostemplate: str = Field(..., description="Debian 12 standard template path")
    memory: int = 1024
    cores: int = 2
    net0: str = Field(
        "name=eth0,bridge=vmbr0,ip=dhcp",
        description="Prefer fixed LAN IP once Wil locks address; OPNsense TCP/445",
    )
    rootfs: str = "local-lvm:8"
    unprivileged: int = Field(
        0,
        description=(
            "0=privileged often simpler for CephFS bind mounts; "
            "1=unprivileged requires idmap cooperation (see Stronghold runbook)"
        ),
    )
    cephfs_mp: str = Field(
        "mp0:/mnt/pve/cephfs/keep,mp=/srv/samba/keep",
        description="Parent keep mount — single SMB export root; no dual-write with app subvols",
    )
    recommended_packages: list[str] = ["samba", "samba-common-bin", "cifs-utils"]
    hard_rules: list[str] = Field(
        default_factory=lambda: [
            "One Samba CT, one LAN share on the keep parent",
            "App subvolumes (immich/syncthing) are exclusive writers — not Samba-writable",
            "No dual-write of the same files via Samba + app",
            "Do not create production CT without Wil + Lamassu gate",
            "Ceph ≠ backup — off-cluster backup still required",
        ]
    )
    notes: str = (
        "Design lock: mount CephFS keep parent, export one SMB share. "
        "Privilege model: prefer privileged CT OR unprivileged + verified idmap "
        "per unprivileged-lxc-cephfs-permission-cooperation.md. "
        "After create: smb.conf, users ↔ FS owners, OPNsense LAN-only 445."
    )


def _plane_down_response(exc: Exception, action: str) -> ActionResponse:
    err = f"{type(exc).__name__}: {exc}"
    status = classify_pve_error(err)
    logger.warning("lxc.%s soft-fail: %s", action, err)
    return ActionResponse(
        success=False,
        error=err,
        data={
            "available": False,
            "action": action,
            "plane": "pve",
            "status": status,
            "pve_host": get_pve_host(),
            "token_configured": token_configured(),
            "hint": "Fix MCP PVE_HOST/token/DNS before CT create; host ops are Lamassu+Wil gated",
        },
    )


@router.post("/create", response_model=ActionResponse)
def create_lxc(req: LXCCreateRequest):
    if not token_configured():
        return ActionResponse(
            success=False,
            error="PVE token not configured",
            data={
                "available": False,
                "action": "create",
                "status": "token_missing",
                "pve_host": get_pve_host(),
            },
        )
    try:
        sess = get_session()
        params = req.model_dump()
        r = sess.post(
            f"{get_pve_host()}/api2/json/nodes/{req.node}/lxc",
            data=params,
            timeout=get_pve_timeout(),
        )
        r.raise_for_status()
        return ActionResponse(success=True, data=r.json().get("data"))
    except Exception as exc:  # noqa: BLE001
        return _plane_down_response(exc, "create")


@router.get("/reverse-proxy-template", response_model=ActionResponse)
def reverse_proxy_template(ostemplate: str):
    template = ReverseProxyTemplate(ostemplate=ostemplate)
    return ActionResponse(success=True, data=template.model_dump())


@router.get("/samba-share-template", response_model=ActionResponse)
def samba_share_template(ostemplate: str):
    """Docs/API guidance for Samba+CephFS keep share CT — no production create."""
    template = SambaShareTemplate(ostemplate=ostemplate)
    return ActionResponse(success=True, data=template.model_dump())


@router.get("/task/{upid}/status", response_model=ActionResponse)
def task_status(node: str, upid: str):
    try:
        sess = get_session()
        r = sess.get(
            f"{get_pve_host()}/api2/json/nodes/{node}/tasks/{upid}/status",
            timeout=get_pve_timeout(),
        )
        r.raise_for_status()
        return ActionResponse(success=True, data=r.json().get("data"))
    except Exception as exc:  # noqa: BLE001
        return _plane_down_response(exc, "task_status")


class ExecRequest(BaseModel):
    node: str
    vmid: int
    command: str = Field(..., description="Command to run inside the LXC")
    confirm: bool = Field(False, description="Must be true to execute")


@router.post("/exec", response_model=ActionResponse)
def lxc_exec(req: ExecRequest):
    if not req.confirm:
        raise HTTPException(400, detail="confirm=True is required for safety")

    try:
        sess = get_session()
        params = {"command": req.command}
        r = sess.post(
            f"{get_pve_host()}/api2/json/nodes/{req.node}/lxc/{req.vmid}/status/exec",
            data=params,
            timeout=get_pve_timeout(),
        )
        r.raise_for_status()
        return ActionResponse(success=True, data=r.json().get("data"))
    except Exception as exc:  # noqa: BLE001
        return _plane_down_response(exc, "exec")
