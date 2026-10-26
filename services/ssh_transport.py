"""SSH transport protocol + paramiko implementation for Wardens setup/collect."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class SSHTransport(Protocol):
    def connect_password(self, host: str, user: str, password: str, port: int = 22) -> None: ...

    def connect_key(self, host: str, user: str, key_path: Path, port: int = 22) -> None: ...

    def run(self, command: str) -> tuple[int, str, str]: ...

    def write_file(self, remote_path: str, data: bytes, mode: int = 0o644) -> None: ...

    def close(self) -> None: ...


class ParamikoSSH:
    """Real SSH via paramiko. Password is used only during connect_password."""

    def __init__(self) -> None:
        self._client = None
        self._password: str | None = None

    def connect_password(self, host: str, user: str, password: str, port: int = 22) -> None:
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=host,
                port=port,
                username=user,
                password=password,
                allow_agent=False,
                look_for_keys=False,
                timeout=30,
            )
        except Exception as exc:  # noqa: BLE001 — surface as OSError for setup
            raise OSError(f"auth failed: {exc}") from exc
        finally:
            # Drop local reference immediately; paramiko may keep session key material only
            password = ""  # noqa: F841
        self._client = client
        self._password = None

    def connect_key(self, host: str, user: str, key_path: Path, port: int = 22) -> None:
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey = paramiko.Ed25519Key.from_private_key_file(str(key_path))
        try:
            client.connect(
                hostname=host,
                port=port,
                username=user,
                pkey=pkey,
                allow_agent=False,
                look_for_keys=False,
                timeout=30,
            )
        except Exception as exc:  # noqa: BLE001
            raise OSError(f"key auth failed: {exc}") from exc
        self._client = client

    def run(self, command: str) -> tuple[int, str, str]:
        if self._client is None:
            raise RuntimeError("SSH not connected")
        _stdin, stdout, stderr = self._client.exec_command(command, timeout=120)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        return code, out, err

    def write_file(self, remote_path: str, data: bytes, mode: int = 0o644) -> None:
        if self._client is None:
            raise RuntimeError("SSH not connected")
        sftp = self._client.open_sftp()
        try:
            # Ensure parent exists
            parent = str(Path(remote_path).parent)
            try:
                sftp.stat(parent)
            except OSError:
                self.run(f"mkdir -p {parent}")
            with sftp.file(remote_path, "wb") as fh:
                fh.write(data)
            sftp.chmod(remote_path, mode)
        finally:
            sftp.close()

    def close(self) -> None:
        self._password = None
        if self._client is not None:
            self._client.close()
            self._client = None


def generate_ed25519_keypair(private_path: Path, comment: str) -> tuple[Path, Path]:
    """Write an OpenSSH ed25519 key pair; returns (private, public) paths."""
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    private_path.parent.mkdir(parents=True, exist_ok=True)
    key = ed25519.Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    )
    private_path.write_bytes(pem)
    private_path.chmod(0o600)

    raw_pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    def _ssh_string(s: bytes) -> bytes:
        return len(s).to_bytes(4, "big") + s

    payload = _ssh_string(b"ssh-ed25519") + _ssh_string(raw_pub)
    pub_path = Path(str(private_path) + ".pub")
    pub_line = f"ssh-ed25519 {base64.b64encode(payload).decode('ascii')} {comment}\n"
    pub_path.write_text(pub_line, encoding="utf-8")
    pub_path.chmod(0o644)
    return private_path, pub_path
