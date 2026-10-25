"""MCP-side node enrollment: one-shot password SSH → install bridge → key auth.

The password is never written to disk. After setup, ClusterMCP initiates all
collect/run traffic; the Warden bridge does not contact MCP.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from services.node_inventory import NodeInventory, NodeRecord
from services.ssh_transport import SSHTransport, generate_ed25519_keypair


class SetupError(Exception):
    """Node setup failed."""


@dataclass
class SetupRequest:
    host: str
    password: str
    ssh_user: str = "root"
    ssh_port: int = 22
    node: str | None = None  # override hostname -s if set


@dataclass
class SetupResult:
    success: bool
    node: str
    host: str
    collector_path: str
    key_name: str
    message: str = ""


DEFAULT_COLLECTOR_REMOTE = "/opt/wardens/bin/wardens-collector"
WARDEN_VERSION = "0.3.0"
COLLECTOR_CAPS = ["lxc:full", "permissions:audit"]


def _local_collector_bin() -> Path:
    env = os.getenv("WARDENS_COLLECTOR_BIN", "").strip()
    if env:
        return Path(env)
    # repo-relative default
    here = Path(__file__).resolve().parent.parent
    candidate = here / "wardens" / "build" / "collector"
    return candidate


def setup_node(
    request: SetupRequest,
    *,
    transport: SSHTransport,
    inventory: NodeInventory,
    keys_dir: Path,
) -> SetupResult:
    if not request.host.strip():
        raise SetupError("host is required")
    if not request.password:
        raise SetupError("password is required for initial setup and is not stored")

    password = request.password
    try:
        transport.connect_password(
            request.host, request.ssh_user, password, port=request.ssh_port
        )
    except OSError as exc:
        raise SetupError(f"auth failed for {request.ssh_user}@{request.host}: {exc}") from exc
    finally:
        # Password must not remain on the request object after connect attempt
        request.password = ""
        password = ""  # noqa: F841

    try:
        return _enroll_connected(request, transport=transport, inventory=inventory, keys_dir=keys_dir)
    finally:
        transport.close()


def _enroll_connected(
    request: SetupRequest,
    *,
    transport: SSHTransport,
    inventory: NodeInventory,
    keys_dir: Path,
) -> SetupResult:
    # --- preflight checks ---
    code, _, _ = transport.run("test -d /etc/pve")
    if code != 0:
        raise SetupError("host is not a Proxmox node (/etc/pve missing)")

    code, out, _ = transport.run("hostname -s")
    hostname = (request.node or out.strip() or "").strip()
    if not hostname:
        raise SetupError("could not determine node name (hostname -s empty)")

    code, pve_out, _ = transport.run("pveversion")
    if code != 0:
        raise SetupError("pveversion failed; host may not be a Proxmox node")

    # --- key material (MCP side) ---
    keys_dir.mkdir(parents=True, exist_ok=True)
    key_name = f"warden-{hostname}"
    private_path = keys_dir / key_name
    if not private_path.is_file():
        private_path, pub_path = generate_ed25519_keypair(private_path, comment=f"clustermcp-{hostname}")
    else:
        pub_path = Path(str(private_path) + ".pub")
        if not pub_path.is_file():
            raise SetupError(f"private key exists without public key: {private_path}")

    pub_line = pub_path.read_text(encoding="utf-8").strip()

    # --- install authorized key ---
    transport.run("mkdir -p /root/.ssh")
    transport.run("chmod 700 /root/.ssh")
    # Avoid duplicate entries
    grep_cmd = f"grep -qxF {shlex.quote(pub_line)} /root/.ssh/authorized_keys"
    code, _, _ = transport.run(grep_cmd)
    if code != 0:
        # append
        append_cmd = f"echo {shlex.quote(pub_line)} >> /root/.ssh/authorized_keys"
        code, _, err = transport.run(append_cmd)
        if code != 0:
            raise SetupError(f"failed to install authorized key: {err}")
        transport.run("chmod 600 /root/.ssh/authorized_keys")

    # --- install collector bridge binary ---
    local_bin = _local_collector_bin()
    if not local_bin.is_file():
        raise SetupError(
            f"collector binary not found at {local_bin}; build with: make -C wardens/build collector"
        )
    data = local_bin.read_bytes()
    transport.run("install -d /opt/wardens/bin /etc/wardens")
    transport.write_file(DEFAULT_COLLECTOR_REMOTE, data, mode=0o755)
    code, _, _ = transport.run(f"test -x {DEFAULT_COLLECTOR_REMOTE}")
    if code != 0:
        raise SetupError("collector binary not executable on remote after install")

    # Drop a minimal env file — node name only; NO ClusterMCP URL (pull model)
    env_body = (
        f"WARDEN_NODE={hostname}\n"
        f"WARDEN_VERSION={WARDEN_VERSION}\n"
    )
    transport.write_file("/etc/wardens/collector.env", env_body.encode(), mode=0o644)

    # --- enroll in inventory (never password) ---
    record = NodeRecord(
        node=hostname,
        host=request.host,
        ssh_user=request.ssh_user,
        ssh_port=request.ssh_port,
        auth_method="ssh_key",
        key_name=key_name,
        collector_path=DEFAULT_COLLECTOR_REMOTE,
        warden_version=WARDEN_VERSION,
        collector_caps=list(COLLECTOR_CAPS),
        runner_allowlist=[],
    )
    inventory.save(record)

    # Mirror enrollment into capabilities store (push-register path deprecated)
    try:
        from routers.wardens import WardenCapabilities, get_store

        get_store().save_capabilities(
            WardenCapabilities(
                node=hostname,
                warden_version=WARDEN_VERSION,
                collector_caps=list(COLLECTOR_CAPS),
                runner_allowlist=[],
                seccomp_profile="none",
                resource_limits={"max_mem_mb": 256},
            )
        )
    except Exception:  # noqa: BLE001 — inventory is SoR; caps mirror is best-effort
        pass

    return SetupResult(
        success=True,
        node=hostname,
        host=request.host,
        collector_path=DEFAULT_COLLECTOR_REMOTE,
        key_name=key_name,
        message=f"enrolled {hostname} ({pve_out.strip().splitlines()[0] if pve_out.strip() else 'pve'})",
    )
