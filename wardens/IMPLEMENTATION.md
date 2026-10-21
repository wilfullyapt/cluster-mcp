# Wardens Implementation Plan (ClusterMCP Visibility Upgrade)

**Date**: 2026-09-29 (MVP progress 2026-10-21)  
**Status**: Phase 0 complete; **Phase 1 collector MVP** in progress for home-lab dogfood.  
**SoR (near-term)**: `/root/seneschal/repos/clustermcp/wardens/` (nested under ClusterMCP; GitHub slug still `proxmox-mcp` until Wil renames)  
**Central integration**: ClusterMCP Python FastAPI (`routers/wardens.py`)  
**ADR**: `reliquary/domains/shipyard/adr/0002-wardens-vs-clustermcp.md`

## Goals

Per-node **C binaries** on each Proxmox host give ClusterMCP host-local visibility (LXC conf, permissions, later CephFS/Docker) and eventually **limited** signed mutate via runner — without interactive SSH for routine status.

**Not** a Proxmox VE marketplace/UI add-on. Packaging may later be a `.deb`; runtime is systemd node agent.

## Components

- **collector/**: Read-oriented C binary. Pushes register + report to ClusterMCP.
- **runner/**: Restricted execution C binary (signed-job only) — **skeleton only in MVP**.
- **shared/**: C structs (`visibility.h`, `job.h`).
- **build/**: Makefile (`gcc` default; `STATIC=1 CC=musl-gcc` optional).
- **docs/**: CAPABILITIES (shipped vs planned), INSTALL-NODE, systemd units.

## Phase status

| Phase | Status |
|-------|--------|
| 0 Data models & contracts | **Done** — headers + Pydantic `CollectorReport` |
| 1 Collector core MVP | **Done for lab** — multi-LXC parse, env URL/node, register+report, file store API, systemd timer templates |
| 2 Runner core | **Not started** — skeleton only |
| 3 CephFS/Docker collectors | **Not started** |
| OpenKEEP extract | **Deferred** until contracts stabilize |

## Build & deployment

```bash
cd wardens/build && make collector
```

- Dynamic `gcc` + libcurl for lab; static musl optional for PVE portability.
- **Ops:** Hephaestus builds; Lamassu installs on PVE nodes (see `docs/INSTALL-NODE.md`).

## Integration with ClusterMCP

Shipped router: `routers/wardens.py` (not separate wardens_collector/jobs modules yet).  
Auth: optional global `MCP_API_KEY` middleware.  
Store: `WARDENS_DATA_DIR` JSON files.

## Packaging

- Near term: nested under ClusterMCP repo (`wardens/`).
- Standalone `/root/seneschal/repos/wardens` is **pointer-only** (ADR 0002).

## Next after lab dogfood

1. Ceph thin collector slice that matches home-lab pain points.  
2. Heartbeat/`last_seen` on register.  
3. Runner Phase 2 only after collector proves useful on all nodes.  
4. OpenKEEP public extract when API freezes.
