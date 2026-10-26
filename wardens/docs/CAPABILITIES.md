# Wardens Capabilities (Collector bridge + Runner)

**Purpose:** Define what each Warden bridge can see/do so ClusterMCP can enroll, gate, and dispatch.

**Control plane:** ClusterMCP owns setup, scheduling, and initiation.  
**Node agent:** C bridge binary installed by `cluster setup`. Not a PVE UI add-on.

## Architecture (current)

```text
operator:  cluster setup --ip <node>   # password ephemeral
           cluster fleet-sync          # build + push all + collect
ClusterMCP  --SSH key-->  wardens-collector (stdout JSON)
ClusterMCP  schedules intervals / runs; bridge never calls MCP
```

## Shipped

### CLI (`cluster`)

| Command | Notes |
|---------|--------|
| `cluster setup --ip <addr>` | Password once; install bridge; enroll; initial collect |
| `cluster nodes` | List enrolled inventory |
| `cluster collect --node <name>` | MCP-initiated pull via bridge |
| `cluster collect --all` | Collect every enrolled node |
| `cluster update --node\|--all` | Push rebuilt bridge via key (no password) |
| `cluster fleet-sync` | **One shot:** build + update all + collect all |

### ClusterMCP HTTP API

| Method | Path | Notes |
|--------|------|--------|
| `GET` | `/wardens/enrolled` | Inventory from `cluster setup` |
| `POST` | `/wardens/nodes/{node}/collect` | Collect one node |
| `POST` | `/wardens/collect-all` | Collect every enrolled node |
| `POST` | `/wardens/nodes/{node}/update` | Push bridge binary |
| `POST` | `/wardens/fleet-sync` | Build + push all + collect (query: build/update/collect) |
| `GET` | `/wardens/nodes/{node}/report` | Last stored report |
| `GET` | `/wardens/reports` | Nodes with a stored report |
| `GET` | `/wardens/nodes` | Capability summaries |
| `GET` | `/wardens/nodes/{node}/capabilities` | Full caps |
| `GET` | `/wardens/capabilities` | Union of cap strings |

**Deprecated:** `POST /wardens/register`, `POST /wardens/collector/report` (push model).

Persistence: `WARDENS_DATA_DIR` — `nodes/`, `ssh/`, `capabilities/`, `reports/`. **No passwords.**

### Collector bridge (`wardens/build/collector`) v0.4.0

| Capability | Status | Behavior |
|------------|--------|----------|
| `lxc:full` | **shipped** | Enumerate `/etc/pve/lxc/*.conf` (up to 64) |
| `permissions:audit` | **shipped** | `stat` + `access` on `/etc/pve/lxc` |
| `host:summary` | **shipped** | loadavg, mem, uptime, kernel, pveversion |
| `cephfs:mapping` | **shipped** | ceph-ish LXC mp* + storage.cfg cephfs names |
| stdout JSON | **shipped** | forced-command `collect`; no MCP URL |

### Runner binary

| Status | Notes |
|--------|--------|
| **Skeleton only** | Do not enable |

## Target state (not shipped)

| Item | Description |
|------|-------------|
| MCP-side interval scheduler | systemd timer calling collect-all |
| OTA post-hook → fleet-sync | Auto after admin update |
| `cephfs:mapping` / `docker:status` | Extra bridge slices |
| Signed runner allow-list | MCP-initiated mutate |

## Enrollment record

```json
{
  "node": "pvenodetwo",
  "host": "192.168.0.242",
  "auth_method": "ssh_key",
  "key_name": "warden-pvenodetwo",
  "collector_path": "/opt/wardens/bin/wardens-collector",
  "warden_version": "0.4.0",
  "collector_caps": ["lxc:full", "permissions:audit", "host:summary"]
}
```

See `INSTALL-NODE.md` and Reliquary `domains/shipyard/maps/clustermcp-wardens-control-plane.md`.
