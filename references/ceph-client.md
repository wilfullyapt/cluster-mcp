# CephClient Implementation Notes (v0.6+)

## Architecture
- Strategy + Adapter pattern in `clients/ceph_client.py`
- Primary: `ProxmoxSDKCephAdapter` (uses proxmox-sdk)
- Future fallback: Direct librados adapter

## Current Endpoints (routers/ceph.py)
- GET /ceph/health
- GET /ceph/status
- GET /ceph/osds
- GET /ceph/fs

## Next Steps
- Real proxmox-sdk integration (replace placeholders)
- Capability gating (`ceph_read`)
- Subvolume listing for CephFS
- Prometheus metrics exposure for OSD usage

## Error Handling
All Ceph errors are wrapped in `CephConnectionError` and returned as HTTP 503.
