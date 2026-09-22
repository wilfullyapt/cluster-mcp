"""Tests for MCP exceptions and action logging funnel."""

import logging
from io import StringIO

from exceptions import (
    CephNotImplementedError,
    MCPException,
)
from logging_config import get_logger


def test_mcp_exception_with_action_logs():
    """Explicit test: MCPException with action= should emit structured log."""
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.ERROR)
    logger = get_logger("mcp.exceptions")
    logger.addHandler(handler)

    try:
        raise CephNotImplementedError(action="ceph_status")
    except CephNotImplementedError as exc:
        assert exc.action == "ceph_status"
        assert exc.status_code == 501

    # Check that a log entry with the action was emitted
    log_output = log_stream.getvalue()
    assert "mcp_exception_raised" in log_output or "ceph_status" in log_output

    logger.removeHandler(handler)


def test_ceph_not_implemented_error():
    exc = CephNotImplementedError(action="ceph_osds")
    assert exc.status_code == 501
    assert exc.detail == "Ceph endpoint not implemented"
    assert exc.action == "ceph_osds"


def test_base_mcp_exception_action():
    exc = MCPException(action="cluster_nodes", detail="test")
    assert exc.action == "cluster_nodes"
