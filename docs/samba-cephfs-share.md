# Samba LXC + CephFS keep share — product guidance (ClusterMCP)

This is **docs/API only**. Production CT create is Lamassu + Wil gated.

## Direction (estate lock)

- **One** Samba LXC
- Mount CephFS **keep** parent (or equivalent)
- Export **one** LAN SMB share
- App subvolumes (Immich/Syncthing) are exclusive writers — **no dual-write** via Samba

## API

```http
GET /lxc/samba-share-template?ostemplate=local:vztmpl/debian-12-standard_….tar.zst
```

Returns hostname defaults, suggested `mp0` keep mount, package list, and hard rules.
Does **not** create a CT.

`POST /lxc/create` will soft-fail with honest `plane` status when PVE DNS/token is down
(`available=false`, `status=pve_unreachable|token_missing|…`).

## Privilege model

| Mode | When |
|------|------|
| Privileged CT (`unprivileged=0`) | Simpler CephFS bind mounts |
| Unprivileged + idmap | Requires Stronghold runbook `unprivileged-lxc-cephfs-permission-cooperation.md` |

## Related MCP endpoints (read)

| Endpoint | Use |
|----------|-----|
| `GET /ceph/fs` | FS name/status + best-effort subvolume list |
| `GET /ceph/fs-subvolumes` | List subvolumes (path/quota/used when PVE exposes them) |
| `GET /ceph/fs-subvolumes/{name}` | One subvolume info |
| `GET /ceph/storage` | PVE CephFS storage IDs (`cephfs`, `cephfs-immich`, …) |
| `GET /report/visibility` | Ops card incl. Wardens + attention `Next:` lines |

## Out of scope here

- Production MCP `.env` DNS/token fix
- Samba CT deploy, smb.conf, OPNsense 445
- Syncthing dual-path cleanup
- Physical OSD work

See Reliquary: `domains/stronghold/runbooks/ceph-samba-keep-immich-syncthing.md`
