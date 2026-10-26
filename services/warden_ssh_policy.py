"""SSH forced-command helpers for Wardens (no open root shell)."""

from __future__ import annotations

import shlex

WRAPPER_REMOTE = "/opt/wardens/bin/wardens-ssh-wrapper"
COLLECTOR_REMOTE = "/opt/wardens/bin/wardens-collector"


def authorized_keys_options(*, from_cidrs: str | None = None) -> str:
    """OpenSSH authorized_keys option prefix for the MCP key."""
    parts = [
        f'command="{WRAPPER_REMOTE}"',
        "no-agent-forwarding",
        "no-port-forwarding",
        "no-X11-forwarding",
        "no-pty",
        "no-user-rc",
    ]
    if from_cidrs and from_cidrs.strip():
        # from="10.0.0.0/8,192.168.0.0/16"
        parts.insert(0, f'from="{from_cidrs.strip()}"')
    return ",".join(parts)


def authorized_keys_line(pubkey_body: str, *, from_cidrs: str | None = None) -> str:
    """Build a single authorized_keys line (pubkey_body is 'ssh-ed25519 AAAA… comment')."""
    body = pubkey_body.strip()
    opts = authorized_keys_options(from_cidrs=from_cidrs)
    return f"{opts} {body}"


def collect_remote_command() -> str:
    """Remote argv when key has forced command — becomes SSH_ORIGINAL_COMMAND."""
    return "collect"


def install_binary_remote_command() -> str:
    return "install-binary"


def version_remote_command() -> str:
    return "version"


def legacy_collect_shell(node: str, collector_path: str = COLLECTOR_REMOTE) -> str:
    """Fallback if node has no wrapper yet (open shell — prefer re-setup)."""
    return (
        "set -a; "
        "[ -f /etc/wardens/collector.env ] && . /etc/wardens/collector.env; "
        "set +a; "
        f"WARDEN_NODE=${{WARDEN_NODE:-{shlex.quote(node)}}} "
        f"{shlex.quote(collector_path)}"
    )
