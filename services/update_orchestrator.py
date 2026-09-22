"""UpdateOrchestrator – centralizes self-update logic with pre-flight and rollback.

This is the single source of truth for the self-maintenance flow.
"""

import subprocess
from pathlib import Path
from typing import Any, Protocol

from config import settings as default_settings
from logging_config import get_logger as default_get_logger


class SettingsProtocol(Protocol):
    mcp_repo_root: Path
    last_known_good_file: Path


class LoggerProtocol(Protocol):
    def info(self, msg: str, **kwargs: Any) -> None: ...
    def error(self, msg: str, **kwargs: Any) -> None: ...


class UpdateOrchestrator:
    def __init__(
        self,
        repo_root: Path | None = None,
        settings: SettingsProtocol | None = None,
        get_logger: Any = None,
    ):
        self.settings = settings or default_settings
        self.get_logger = get_logger or default_get_logger
        self.repo_root = repo_root or self.settings.mcp_repo_root
        self.logger = self.get_logger("update.orchestrator")

    def run_preflight(self) -> tuple[bool, str]:
        """Run ruff + pytest before applying the update (venv-aware)."""
        venv_bin = self.repo_root / ".venv" / "bin"
        ruff_cmd = str(venv_bin / "ruff") if (venv_bin / "ruff").exists() else "ruff"
        python_cmd = str(venv_bin / "python") if (venv_bin / "python").exists() else "python"

        try:
            ruff = subprocess.run(
                [ruff_cmd, "check", ".", "--fix"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if ruff.returncode != 0:
                return False, f"ruff failed:\n{ruff.stdout}\n{ruff.stderr}"

            pytest = subprocess.run(
                [python_cmd, "-m", "pytest", "-q", "--tb=no"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if pytest.returncode != 0:
                return False, f"pytest failed:\n{pytest.stdout}\n{pytest.stderr}"

            return True, "Pre-flight checks passed"
        except Exception as exc:
            return False, f"Pre-flight error: {exc}"

    def _health_check(self) -> bool:
        """Basic post-update health check."""
        try:
            import main  # noqa: F401
            return True
        except Exception as exc:
            self.logger.error("Post-update health check failed", error=str(exc))
            return False

    def record_last_known_good(self) -> str:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.repo_root, text=True
        ).strip()
        self.settings.last_known_good_file.write_text(commit)
        self.logger.info("Recorded last-known-good", commit=commit)
        return commit

    def perform_update(self, ref: str, force: bool = False) -> dict[str, Any]:
        """High-level update flow with pre-flight and rollback support.

        More robust git handling:
        - Always clean working tree before update
        - Use reset --hard to origin/ref for reliable fast-forwards
        - Handles untracked files (e.g. .last_known_good)
        """
        self.logger.info("Starting orchestrated update", ref=ref, force=force)

        try:
            current = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=self.repo_root, text=True
            ).strip()
        except Exception:
            current = "unknown"

        # Pre-flight
        ok, msg = self.run_preflight()
        if not ok:
            self.logger.error("Pre-flight failed", msg=msg)
            return {"success": False, "error": msg}

        # Robust Git sequence
        # Build venv-aware commands
        venv_bin = self.repo_root / ".venv" / "bin"
        pip_cmd = str(venv_bin / "pip") if (venv_bin / "pip").exists() else "pip"

        commands = [["git", "fetch", "origin"]]

        if force:
            commands.append(["git", "reset", "--hard", f"origin/{ref}"])
        else:
            # Clean any untracked files (e.g. .last_known_good) then hard reset to origin
            commands.append(["git", "clean", "-fd"])
            commands.append(["git", "checkout", "-B", ref, f"origin/{ref}"])
            commands.append(["git", "reset", "--hard", f"origin/{ref}"])

        commands.append([pip_cmd, "install", "-r", "requirements.txt", "--quiet"])

        output_lines = []
        for cmd in commands:
            self.logger.info("Running command", cmd=" ".join(cmd))
            result = subprocess.run(
                cmd, cwd=self.repo_root, capture_output=True, text=True, timeout=180
            )
            output_lines.append(f"$ {' '.join(cmd)}\n{result.stdout}{result.stderr}")
            if result.returncode != 0:
                self.logger.error("Command failed", cmd=cmd)
                if current != "unknown":
                    self.logger.warning("Rolling back to previous commit", commit=current)
                    subprocess.run(["git", "reset", "--hard", current], cwd=self.repo_root)
                return {
                    "success": False,
                    "error": f"Command failed: {' '.join(cmd)} (venv/pip issue? check .venv/bin/pip)",
                    "output": "\n".join(output_lines),
                }

        # Post-update health check with automatic rollback
        if not self._health_check():
            self.logger.error("Post-update health check failed — rolling back")
            if current != "unknown":
                subprocess.run(["git", "reset", "--hard", current], cwd=self.repo_root)
            return {
                "success": False,
                "error": "Post-update health check failed",
                "output": "\n".join(output_lines),
            }

        # Success - restart service
        restarted, restart_msg = self._restart_service() if hasattr(self, "_restart_service") else (True, "No restart method")
        self.record_last_known_good()
        self.logger.info("Update completed successfully", ref=ref, restarted=restarted)
        return {
            "success": True,
            "message": f"Update to {ref} completed. Restart: {restart_msg}",
            "output": "\n".join(output_lines),
        }

    def _restart_service(self) -> tuple[bool, str]:
        """Restart the MCP service after a successful update.

        Preferred: systemctl
        Fallback: pkill uvicorn (relies on systemd Restart=always)
        """
        try:
            result = subprocess.run(
                ["systemctl", "restart", "proxmox-mcp"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                self.logger.info("Service restarted via systemctl")
                return True, "systemctl restart successful"

            self.logger.warning("systemctl restart failed, trying pkill fallback")
            subprocess.run(["pkill", "-f", "uvicorn"], capture_output=True, timeout=10)
            return True, "pkill fallback (systemd Restart=always will respawn)"

        except Exception as exc:
            self.logger.error("Restart failed", error=str(exc))
            return False, f"restart error: {exc}"
