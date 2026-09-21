"""Unit tests for the dedicated CephClient (Strategy + Adapter pattern)."""




def test_health_no_client(ceph_client_mock):
    result = ceph_client_mock.get_health()
    assert result == {"status": "HEALTH_OK"}


def test_get_osd_status_no_client(ceph_client_mock):
    result = ceph_client_mock.get_osds()
    assert result == []


def test_get_pool_stats_no_client(ceph_client_mock):
    # Placeholder until real pool stats endpoint is added
    assert ceph_client_mock.get_status() is not None


def test_get_cephfs_usage_no_client(ceph_client_mock):
    result = ceph_client_mock.get_fs()
    assert result == {"name": "cephfs", "status": "active", "subvolumes": []}
