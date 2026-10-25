# Wardens Capabilities (Collector bridge + Runner)

**Purpose:** Define what each Warden bridge can see/do so ClusterMCP can enroll, gate, and dispatch.

**Control plane:** ClusterMCP owns setup, scheduling, and initiation.  
**Node agent:** C bridge binary installed by `cluster setup`. Not a PVE UI add-on.

## Architecture (current)

```text
operator:  cluster setup --ip <node>   # password ephemeral
ClusterMCP  --SSH key-->  wardens-collector (stdout JSON)
ClusterMCP  schedules intervals / runs; bridge never calls MCP
```

## Shipped

### CLI (`cluster`)

| Command | Notes |
|---------|--------|
| `cluster setup --ip <addr>` | Password prompt/stdin; install bridge; enroll node |
| `cluster nodes` | List enrolled inventory |
| `cluster collect --node <name>` | MCP-initiated pull via bridge |

### ClusterMCP HTTP API

| Method | Path | Notes |
|--------|------|--------|
| `GET` | `/wardens/enrolled` | Inventory from `cluster setup` |
| `POST` | `/wardens/nodes/{node}/collect` | MCP-initiated collect over SSH bridge |
| `GET` | `/wardens/nodes/{node}/report` | Last stored report |
| `GET` | `/wardens/reports` | Nodes with a stored report |
| `GET` | `/wardens/nodes` | Capability summaries (mirrored on enroll) |
| `GET` | `/wardens/nodes/{node}/capabilities` | Full caps document |
| `GET` | `/wardens/capabilities` | Union of cap strings |

**Deprecated (push model):** `POST /wardens/register`, `POST /wardens/collector/report` remain for transition/tests but are **not** the setup path. Bridges do not call them.

Persistence: `WARDENS_DATA_DIR` (default `/var/lib/clustermcp/wardens`) — `nodes/`, `ssh/`, `capabilities/`, `reports/`. **Passwords never stored.**

### Collector bridge (`wardens/build/collector`)

| Capability | Status | Behavior |
|------------|--------|----------|
| `lxc:full` | **MVP** | Enumerate `/etc/pve/lxc/*.conf` (up to 64) |
| `permissions:audit` | **MVP** | `stat` + `access` on `/etc/pve/lxc` |
| stdout JSON report | **MVP** | Env: `WARDEN_NODE`, optional `WARDEN_VERSION` |
| Outbound to MCP | **Removed** | Bridge has no MCP URL |

### Runner binary

| Status | Notes |
|--------|--------|
| **Skeleton only** | No signing/seccomp/jobs. **Do not enable.** |

## Target state (not shipped)

| Item | Description |
|------|-------------|
| MCP-side interval scheduler | systemd timer / internal job on MCP host |
| `cephfs:mapping` / `docker:status` | Extra bridge collect slices |
| Signed runner allow-list | MCP-initiated mutate jobs |
| mTLS or SSH CA | Stronger node auth than per-node keys |

## Enrollment record (inventory — shipped)

```json
{
  "node": "pvenodeone",
  "host": "192.168.0.10",
  "ssh_user": "root",
  "ssh_port": 22,
  "auth_method": "ssh_key",
  "key_name": "warden-pvenodeone",
  "collector_path": "/opt/wardens/bin/wardens-collector",
  "warden_version": "0.3.0",
  "collector_caps": ["lxc:full", "permissions:audit"],
  "runner_allowlist": []
}
```

See `INSTALL-NODE.md` and `../IMPLEMENTATION.md`.
