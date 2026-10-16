# Wardens Implementation Plan (ClusterMCP Visibility Upgrade)

**Date**: 2026-09-29
**Status**: Locked. All pins confirmed (C static binaries, wardens/ mono-repo, collector vs runner split, signing model, Stronghold dogfood first).
**Repo base**: /root/butler/stronghold/wardens/
**Central integration**: Extend existing /root/butler/stronghold/clustermcp (Python FastAPI in LXC 106).

## Goals (recap)
Deliver the 5 visibility areas via per-node C agents (Wardens) so the central MCP can see everything inside LXCs, host/container permissions, CephFS mappings, Docker status, etc., without SSH.

## Components
- **collector/**: Read-only C binary (systemd service). Gathers and serves/pushes the 5 visibility datasets.
- **runner/**: Restricted execution C binary (separate systemd service). Signed-job only.
- **shared/**: Common headers, data models (C structs + JSON schemas), signing helpers, protocol.
- **scripts/**: node-join.sh, build scripts, signing wrappers.
- **build/**: Makefiles, musl/zig cross-compile setup for static binaries.
- **docs/**: Runbooks, allow-list examples, threat model.

## Phase 0 (now) – Data Models & Contracts
1. Define the 5 visibility areas as stable C structs + JSON schema (for MCP API).
   - LXC: config, mounts, idmaps, UID/GID mappings, status.
   - CephFS: subvolumes, host-side ownership/permissions, quotas.
   - Docker: compose projects, container status, networks/volumes for known paths.
   - Permissions/UID: effective UID mapping, capability checks, ownership audits.
   - Troubleshooting bundles: aggregated diagnostics (logs, resource usage, error states).
2. Define job schema (for runner).
3. Define wire protocol (mTLS + JSON or simple binary framing).
4. Create shared/visibility.h and shared/job.h.

## Phase 1 – Collector Core
- Static C binary using libcurl or simple socket for MCP communication.
- Systemd unit template.
- node-join.sh that installs binary + registers.
- Endpoints in central MCP to consume collector data.

## Phase 2 – Runner Core
- Job verification (signature + allow-list).
- seccomp-bpf filter (minimal syscall set).
- Resource limits via cgroups or prlimit.
- Full audit logging back to MCP.
- Small allow-list starter set (restart services, log collection, safe reads).

## Build & Deployment
- Static linking with musl libc (or zig cc) for PVE node compatibility.
- Signing: minisign or ed25519 (MCP holds private key).
- Deployment: systemd on each PVE node; central MCP polls or receives pushes.

## Integration with clustermcp
- New routers in central MCP (wardens_collector.py, wardens_jobs.py).
- Reuse existing auth, logging, ActionResponse model.
- Metrics exposed to hermes-monitor.

## Next Immediate Steps
1. Define data model structs (this file will be updated with them).
2. Create initial shared/ headers.
3. Skeleton collector main.c with registration flow.
4. Update central MCP with first consumer endpoint.

All code stays under /root/butler/stronghold/wardens/ until OpenKEEP extraction.