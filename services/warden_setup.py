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


class UpdateError(Exception):
    """Warden binary update failed."""


@dataclass
class SetupRequest:
    host: str
    password: str
    ssh_user: str = "root"
    ssh_port: int = 22
    node: str | None = None  # override hostname -s if set
    collect_after: bool = True


@dataclass
class SetupResult:
    success: bool
    node: str
    host: str
    collector_path: str
    key_name: str
    message: str = ""
    initial_report: dict | None = None


@dataclass
class UpdateResult:
    success: bool
    node: str
    collector_path: str
    warden_version: str
    message: str = ""


DEFAULT_COLLECTOR_REMOTE = "/opt/wardens/bin/wardens-collector"
WARDEN_VERSION = "0.5.0"
COLLECTOR_CAPS = ["lxc:full", "permissions:audit", "host:summary", "cephfs:mapping"]


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
        result = _enroll_connected(
            request, transport=transport, inventory=inventory, keys_dir=keys_dir
        )
    finally:
        transport.close()

    if request.collect_after:
        from services.warden_bridge import BridgeError, collect_node

        try:
            report = collect_node(
                result.node,
                inventory=inventory,
                keys_dir=keys_dir,
            )
            result.initial_report = report
            result.message = f"{result.message}; initial collect ok (lxc={len(report.get('lxc') or [])})"
        except BridgeError as exc:
            result.message = f"{result.message}; initial collect failed: {exc}"
    return result


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
    from_cidrs = os.getenv("WARDENS_SSH_FROM", "").strip() or None
    from services.warden_ssh_policy import (
        WRAPPER_REMOTE,
        authorized_keys_line,
    )

    ak_line = authorized_keys_line(pub_line, from_cidrs=from_cidrs)
    # key material (base64) for scrubbing old unrestricted lines
    parts = pub_line.split()
    key_mat = parts[1] if len(parts) >= 2 else pub_line

    # --- install SSH wrapper + bridge (password session = full shell once) ---
    local_bin = _local_collector_bin()
    if not local_bin.is_file():
        raise SetupError(
            f"collector binary not found at {local_bin}; build with: make -C wardens/build collector"
        )
    wrapper_src = Path(__file__).resolve().parent.parent / "wardens" / "docs" / "scripts" / "wardens-ssh-wrapper.sh"
    if not wrapper_src.is_file():
        raise SetupError(f"SSH wrapper missing: {wrapper_src}")

    transport.run("install -d /opt/wardens/bin /etc/wardens /root/.ssh")
    transport.run("chmod 700 /root/.ssh")
    transport.write_file(WRAPPER_REMOTE, wrapper_src.read_bytes(), mode=0o755)
    transport.write_file(DEFAULT_COLLECTOR_REMOTE, local_bin.read_bytes(), mode=0o755)
    code, _, _ = transport.run(f"test -x {DEFAULT_COLLECTOR_REMOTE} && test -x {WRAPPER_REMOTE}")
    if code != 0:
        raise SetupError("collector or SSH wrapper not executable on remote after install")

    # Scrub prior lines for this key, install forced-command line only
    scrub = (
        f"touch /root/.ssh/authorized_keys; "
        f"grep -v {shlex.quote(key_mat)} /root/.ssh/authorized_keys > /tmp/wardens-ak.new || true; "
        f"echo {shlex.quote(ak_line)} >> /tmp/wardens-ak.new; "
        f"mv /tmp/wardens-ak.new /root/.ssh/authorized_keys; "
        f"chmod 600 /root/.ssh/authorized_keys"
    )
    code, _, err = transport.run(scrub)
    if code != 0:
        raise SetupError(f"failed to install restricted authorized_keys: {err}")

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
        auth_method="ssh_key_forced",
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


def update_warden_binary(
    node: str,
    *,
    inventory: NodeInventory,
    keys_dir: Path,
    transport: SSHTransport,
    version: str = WARDEN_VERSION,
) -> UpdateResult:
    """Push a freshly built bridge binary using the enrolled SSH key (no password)."""
    rec = inventory.get(node)
    if rec is None:
        raise UpdateError(f"node not enrolled: {node}")

    key_path = keys_dir / rec.key_name
    if not key_path.is_file():
        raise UpdateError(f"SSH private key missing for {node}: {key_path}")

    local_bin = _local_collector_bin()
    if not local_bin.is_file():
        raise UpdateError(
            f"collector binary not found at {local_bin}; build with: make -C wardens/build collector"
        )

    owns = not getattr(transport, "connected", False)
    try:
        if owns:
            transport.connect_key(rec.host, rec.ssh_user, key_path, port=rec.ssh_port)

        from services.warden_ssh_policy import WRAPPER_REMOTE, install_binary_remote_command

        payload = local_bin.read_bytes()
        run_stdin = getattr(transport, "run_stdin", None)
        mode = "install-binary"
        if run_stdin is not None:
            code, out, err = run_stdin(install_binary_remote_command(), payload)
        else:
            code, out, err = 1, "", "no run_stdin"

        # Legacy enrollments: open SSH shell, no forced-command wrapper yet
        if code != 0 and "command not found" in (err + out).lower():
            mode = "legacy-sftp"
            wrapper_src = (
                Path(__file__).resolve().parent.parent
                / "wardens"
                / "docs"
                / "scripts"
                / "wardens-ssh-wrapper.sh"
            )
            transport.run("install -d /opt/wardens/bin /etc/wardens")
            if wrapper_src.is_file():
                transport.write_file(WRAPPER_REMOTE, wrapper_src.read_bytes(), mode=0o755)
            transport.write_file(rec.collector_path, payload, mode=0o755)
            code, _, test_err = transport.run(f"test -x {rec.collector_path}")
            if code != 0:
                raise UpdateError(
                    f"legacy install failed on {node}: {test_err.strip()} "
                    f"(after install-binary rejected: {err.strip() or out.strip()})"
                )
            env_body = f"WARDEN_NODE={rec.node}\nWARDEN_VERSION={version}\n"
            transport.write_file("/etc/wardens/collector.env", env_body.encode(), mode=0o644)
            out = '{"ok":true,"mode":"legacy-sftp"}'
        elif code != 0:
            raise UpdateError(
                f"install-binary failed on {node}: {err.strip() or out.strip()} "
                "(re-run cluster setup --ip <node> once to install forced-command wrapper)"
            )

        rec.warden_version = version
        inventory.save(rec)
        return UpdateResult(
            success=True,
            node=rec.node,
            collector_path=rec.collector_path,
            warden_version=version,
            message=f"updated bridge on {rec.node} to {version} via {mode}",
        )
    finally:
        if owns:
            transport.close()
