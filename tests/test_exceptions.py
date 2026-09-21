"""Tests for domain exceptions."""

from exceptions import (
    CephConnectionError,
    CephPermissionError,
    MCPException,
    http_exception_from_mcp,
)


def test_base_exception():
    exc = MCPException()
    assert exc.status_code == 500


def test_ceph_connection_error():
    exc = CephConnectionError()
    assert exc.status_code == 503
    assert "Ceph" in exc.detail


def test_permission_error():
    exc = CephPermissionError()
    assert exc.status_code == 403


def test_http_exception_mapper():
    exc = CephConnectionError()
    http_exc = http_exception_from_mcp(exc)
    assert http_exc.status_code == 503
    assert "Ceph" in http_exc.detail
