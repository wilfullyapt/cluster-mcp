"""Tests for Wardens SSH forced-command policy."""

from __future__ import annotations

from services.warden_ssh_policy import (
    authorized_keys_line,
    authorized_keys_options,
    collect_remote_command,
    install_binary_remote_command,
)


def test_authorized_keys_forces_wrapper_and_locks_session() -> None:
    opts = authorized_keys_options()
    assert 'command="/opt/wardens/bin/wardens-ssh-wrapper"' in opts
    assert "no-port-forwarding" in opts
    assert "no-pty" in opts


def test_authorized_keys_optional_from_cidr() -> None:
    opts = authorized_keys_options(from_cidrs="192.168.0.0/24,10.0.0.5")
    assert 'from="192.168.0.0/24,10.0.0.5"' in opts


def test_authorized_keys_line_shape() -> None:
    line = authorized_keys_line(
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest clustermcp-pvenodeone",
        from_cidrs="192.168.0.233",
    )
    assert line.startswith('from="192.168.0.233",command=')
    assert line.endswith("clustermcp-pvenodeone")
    assert "AAAAC3NzaC1lZDI1NTE5AAAAItest" in line


def test_remote_commands_are_allowlisted_tokens() -> None:
    assert collect_remote_command() == "collect"
    assert install_binary_remote_command() == "install-binary"
