# Wardens Capabilities (Collector + Runner)

**Purpose:** Define what each Warden can see and do so ClusterMCP can discover, gate, and dispatch.

**Node agent model:** C binaries installed on each **Proxmox host** (systemd). Not a Proxmox VE UI add-on / marketplace package — a Stronghold node agent.

## Shipped in this branch (MVP)

### ClusterMCP HTTP API

| Method | Path | Notes |
|--------|------|--------|
| `POST` | `/wardens/register` | Capability registration (JSON file store) |
| `GET` | `/wardens/nodes` | Map of node → high-level caps |
| `GET` | `/wardens/nodes/{node}/capabilities` | Full caps document |
| `GET` | `/wardens/capabilities` | Union of all collector/runner cap strings |
| `POST` | `/wardens/collector/report` | Validated collector report (`CollectorReport`) |
| `GET` | `/wardens/nodes/{node}/report` | Last stored report |
| `GET` | `/wardens/reports` | Nodes that have a report |

Persistence: `WARDENS_DATA_DIR` (default `/var/lib/clustermcp/wardens`) — `capabilities/*.json`, `reports/*.json`.

### Collector binary (`wardens/build/collector`)

| Capability | Status | Behavior |
|------------|--------|----------|
| `lxc:full` | **MVP** | Enumerate `/etc/pve/lxc/*.conf` (up to 64) |
| `permissions:audit` | **MVP** | `stat` + `access` on `/etc/pve/lxc` |
| Register + report push | **MVP** | Env: `CLUSTERMCP_URL`, `WARDEN_NODE`, optional `MCP_API_KEY` |

### Runner binary (`wardens/build/runner`)

| Status | Notes |
|--------|--------|
| **Skeleton only** | No signing, seccomp, or job execution. **Do not enable in production.** |

## Target state (not shipped)

### Future collector capabilities

| Capability | Description |
|------------|-------------|
| `cephfs:mapping` | Subvolumes, host ownership, quotas |
| `docker:status` | Compose projects on known paths |
| `troubleshoot:bundle` | Aggregated diagnostics |

### Future runner allow-list (signed jobs only)

| allowlist_key | Description |
|---------------|-------------|
| `service:restart` | Restart allow-listed systemd units |
| `logs:collect` | Scoped journal/log collection |
| `compose:restart` | Scoped compose restart |
| `config:safe-read` | Read approved config paths |
| `diagnostics:run` | Pre-approved diagnostic commands |

### Capability report format (register body — shipped)

```json
{
  "node": "pvenodeone",
  "warden_version": "0.2.0",
  "collector_caps": ["lxc:full", "permissions:audit"],
  "runner_allowlist": [],
  "seccomp_profile": "none",
  "resource_limits": {"max_mem_mb": 256}
}
```

## Cross-cutting (planned)

- `self:update` — signed binary self-update
- `metrics:export` — Prometheus
- `audit:stream` — job/visibility audit feed
- mTLS between Warden and ClusterMCP

See `INSTALL-NODE.md` for lab install and `../IMPLEMENTATION.md` for phasing.
