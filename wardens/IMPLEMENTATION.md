# Wardens Implementation Plan (ClusterMCP control plane)

**Date**: 2026-09-29 (control-plane pivot 2026-10-25)  
**Status**: Push-collector superseded; **MCP-initiated bridge** is the setup path.  
**SoR (near-term)**: `/root/seneschal/repos/clustermcp/wardens/` (GitHub `wilfullyapt/cluster-mcp`)  
**Central integration**: ClusterMCP Python (`cluster` CLI, `services/warden_*.py`, `routers/wardens.py`)  
**ADR**: `reliquary/domains/shipyard/adr/0002-wardens-vs-clustermcp.md`

## Goals

Per-node **C bridge** on each Proxmox host. ClusterMCP:

1. Enrolls nodes via `cluster setup` (password once, never stored)
2. Holds SSH keys + inventory under `WARDENS_DATA_DIR`
3. Initiates all collect/run traffic
4. Owns interval scheduling

The bridge does **not** know MCP’s URL and never opens outbound connections to MCP.

**Not** a Proxmox VE marketplace/UI add-on.

## Components

| Piece | Role |
|-------|------|
| `cluster` CLI | `setup` / `nodes` / `collect` |
| `services/warden_setup.py` | Password SSH → checks → key → install binary |
| `services/warden_bridge.py` | Key SSH → run collector → parse stdout → store |
| `services/node_inventory.py` | Enrolled nodes (no passwords) |
| `wardens/collector/` | stdout JSON bridge (`lxc` + permissions) |
| `wardens/runner/` | Skeleton only |
| `routers/wardens.py` | HTTP: enrolled, collect, reports |

## Phase status

| Phase | Status |
|-------|--------|
| 0 Data models & contracts | **Done** |
| 1 Push collector MVP | **Superseded** (HTTP ingest kept for tests/transition) |
| 1b MCP setup + pull bridge | **Landed on feature branch** |
| 2 Runner core | **Not started** — skeleton only |
| 3 CephFS/Docker collectors | **Not started** |
| OpenKEEP extract | **Deferred** |

## Build & deployment

```bash
cd wardens/build && make collector
cluster setup --ip <node-ip>
```

- No libcurl on the bridge. Static musl optional: `make STATIC=1 CC=musl-gcc collector`
- **Ops:** Hephaestus builds; operator/Lamassu runs `cluster setup` from MCP host (see `docs/INSTALL-NODE.md`).

## Integration with ClusterMCP

- Inventory: `$WARDENS_DATA_DIR/nodes/*.json` + `ssh/warden-*` keys  
- Reports: same store as before via MCP-initiated collect  
- Auth to API: optional global `MCP_API_KEY` middleware  
- Deprecated push: `POST /wardens/register`, `POST /wardens/collector/report`

## Packaging

- Near term: nested under ClusterMCP repo (`wardens/`).
- Standalone `/root/seneschal/repos/wardens` is **pointer-only** (ADR 0002).

## Next

1. MCP-side interval scheduler (cron/systemd calling `cluster collect` or HTTP).
2. Ceph thin bridge slice for home-lab pain points.
3. Runner Phase 2 only after pull-collect proves useful on all nodes.
4. OpenKEEP public extract when API freezes.
