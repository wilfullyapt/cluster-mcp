"""Pydantic models for Proxmox MCP (priv-aware, validated)."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class ActionResponse(BaseModel):
    success: bool
    data: Any | None = None
    error: str | None = None


class LXCCreateRequest(BaseModel):
    node: str = Field(..., description="Proxmox node name")
    vmid: int = Field(..., ge=100, le=999999, description="Unique VMID for the container")
    hostname: str = Field(..., min_length=1, max_length=64)
    ostemplate: str = Field(..., description="Full path to OS template (e.g. local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst)")
    storage: str = "local-lvm"
    memory: int = Field(512, ge=128, le=65536)
    cores: int = Field(1, ge=1, le=32)
    net0: str = Field(
        "name=eth0,bridge=vmbr0,ip=dhcp",
        description="Network config (bridge, IP, VLAN, etc.)"
    )
    rootfs: str = "local-lvm:8"
    unprivileged: int = 1

    @field_validator("net0")
    @classmethod
    def validate_net0(cls, v: str) -> str:
        if "bridge=" not in v:
            raise ValueError("net0 must include bridge=")
        return v


class CapabilitiesResponse(BaseModel):
    permissions: dict[str, Any]
    enabled_features: dict[str, bool]


# --- Ceph response models ---------------------------------------------------

class CephHealthResponse(BaseModel):
    fsid: str | None = None
    status: str
    stats: dict[str, Any] | None = None


class CephOSDResponse(BaseModel):
    status: str
    osds: list[dict[str, Any]] | None = None


class CephPoolStatsResponse(BaseModel):
    status: str
    pools: list[str] | None = None
    count: int | None = None


class CephFSUsageResponse(BaseModel):
    status: str
    usage: dict[str, Any] | None = None
