"""Tests for UpdateOrchestrator."""

from unittest.mock import MagicMock, patch

import pytest

from services.update_orchestrator import UpdateOrchestrator


@pytest.fixture
def orchestrator(tmp_path, monkeypatch):
    monkeypatch.setattr("config.settings.mcp_repo_root", tmp_path)
    return UpdateOrchestrator(repo_root=tmp_path)


def test_run_preflight_success(orchestrator):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        ok, msg = orchestrator.run_preflight()
        assert ok is True


def test_perform_update_success(orchestrator):
    with patch.object(orchestrator, "run_preflight", return_value=(True, "ok")), \
         patch.object(orchestrator, "record_last_known_good"), \
         patch("subprocess.check_output", return_value=b"abc123"), \
         patch("subprocess.run") as mock_run:

        mock_run.return_value = MagicMock(returncode=0)
        result = orchestrator.perform_update("origin/main")
        assert result.get("success") is True


def test_perform_update_preflight_failure(orchestrator):
    with patch.object(orchestrator, "run_preflight", return_value=(False, "ruff failed")):
        result = orchestrator.perform_update("origin/main")
        assert result["success"] is False
