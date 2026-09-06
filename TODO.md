# Proxmox MCP TODOs — Building Out API-Controlled Systems

This MCP provides repeatable, auditable access to Proxmox systems. Future expansions should stay read-heavy for status/automation while gating write actions.

## High Priority (Core Repeatable Tools)
- [ ] Expand `/resources` with filters (node, type, status) and IP/MAC inventory extraction.
- [ ] `/ceph/*` enhancements: pool status, OSD tree, recovery progress, rebalance planning.
- [ ] `/tasks/recent` + filters (user, type, since, status) + cancellation support for stuck tasks.
- [ ] Node-level: CPU/mem/disk usage, services status, version info.
- [ ] Storage: datastore list, content (ISOs, templates, backups), usage stats.

## Medium Priority (VM/LXC Lifecycle & Power)
- [ ] Full VM/container CRUD helpers (clone from template, resize disk, migrate, snapshot/rollback) — keep behind auth or role checks.
- [ ] Power actions already present; add bulk operations and confirmation for destructive.
- [ ] Network config: bridge/VLAN info per VM, IPAM integration ideas.

## Ceph & Storage Management
- [ ] Pool create/resize/delete (with safety checks).
- [ ] OSD add/remove/maintenance mode.
- [ ] RBD image listing and snapshot management.
- [ ] Backup/restore job status and scheduling hooks.

## SDN & Network
- [ ] SDN zones, VNets, subnets status and config.
- [ ] Firewall rules audit (datacenter + VM level).
- [ ] DNS/DHCP integration points.

## Advanced / Integration
- [ ] `/health/snapshot` enrichment: trend data, alerts on thresholds (integrate with hermes-monitor).
- [ ] Task automation: watch for specific task types and trigger downstream (e.g., post-clone config).
- [ ] Authentication/ACL proxy: expose limited PVE user management for service accounts.
- [ ] Metrics export (Prometheus-compatible) for Ceph, nodes, VMs.
- [ ] Webhook/callback support for long-running tasks.
- [ ] OpenKEEP template extraction: parameterize LXC creation, add example GitHub Actions for deploy.

## Non-Functional
- [ ] Rate limiting + request logging with PII redaction.
- [ ] Comprehensive error mapping from PVE responses.
- [ ] Tests (pytest) for endpoints with mocked PVE.
- [ ] CI: lint, security scan (bandit), build Docker, smoke test.
- [ ] Documentation: OpenAPI enhancements, sequence diagrams for common flows (Ceph recovery, VM provisioning).

## How to Contribute / Build
1. Add endpoint in `main.py` following existing pattern (get_session, try/except → ActionResponse).
2. Document in README + add to health_snapshot if applicable.
3. Update permissions-cheatsheet if new privs needed.
4. Test against real cluster (with read-only token first).
5. Keep philosophy: repeatable & safe; one-off work stays on direct SSH/pct/qm.

Target: make this the canonical, clone-and-run component for any Proxmox homelab/OpenKEEP deployment.
## Live Probe Findings — 2026-09-04 (feature/mcp-robustness-fixes)
Observed via direct HTTP probes against running LXC (192.168.0.233:8000) against real cluster:

### Issues Found
- **Pydantic response model mismatch**: `/nodes` and `/resources` return lists but models expect dict → validation errors in ActionResponse. Fix: make models accept list or Union, or normalize in pve_client.py.
- **Missing `/capabilities` endpoint**: Priv-aware mapping (from skill) not present. Returns 404. Implement as planned on feature/priv-aware-tools (call PVE /access/permissions and map to features like read_audit, vm_power, etc.).
- **Ceph OSDs**: `/ceph/osds` → 501 "Method 'GET /cluster/ceph/osd' not implemented". Either PVE version or endpoint path needs update (try /cluster/ceph/osds or handle gracefully).
- **Tasks endpoint**: `/tasks/recent` → 400 "Parameter verification failed" on PVE side. Likely needs explicit `limit` or other params; add defaults/filters.
- **Token ACLs still insufficient**: 403s on cluster/ceph (Sys.Audit etc.) — separate from code but document required role in references/.
- **Positive**: `/health`, `/health/snapshot` solid and useful (3 nodes online, ceph error surfaced cleanly). Version 0.2.0 matches.

### Suggested Improvements (beyond existing TODO)
- Add robust error handling + structured PVE error mapping (currently some bare 403/501 leak).
- Enhance logging_config for self-monitoring (as per stronghold-proxmox-mcp skill).
- Update OpenAPI/models to prevent validation failures on real responses.
- Add integration test or smoke test against live token (with read-only ACL).
- Once ACL fixed, expand snapshot to include more metrics.
- Consider making branch default or merging priv-aware work here.

Next: Apply ACL on PVE, test fixes, push branch.

## Branch Status — feature/mcp-robustness-fixes (2026-09-04)
- [x] Fixed `ActionResponse.data` typing (Any instead of strict dict) — eliminates Pydantic validation errors on list responses from `/nodes` and `/resources`.
- [x] Cleaned duplicate `setup_self_logging()` / logger lines in `main.py`.
- [ ] Ceph OSDs path / error handling (501 on current PVE).
- [ ] `/tasks/recent` param defaults.
- [ ] Verify `/capabilities` works end-to-end once LXC updated.
- [ ] Add smoke test for core endpoints.
- [ ] Prepare LXC update instructions.

Pushed to GitHub after these core robustness fixes.

## Admin / Self-Update Feature (feature/admin-self-update)
- [x] POST /admin/update endpoint (ref, force, dry_run support started)
- [x] Protected by MCP_API_KEY + existing security
- [x] Basic test in tests/test_admin.py
- [ ] Full safety (ref whitelist, always delegate to scripts/update.sh, dry-run mode)
- [ ] Update README with usage example
- [ ] Clean test harness for middleware/dependency

This enables Hermes to keep the MCP current autonomously.

## Stronghold MCP Visibility Report & Integration (feature/stronghold-mcp-visibility-report — started 2026-09-05)
- [x] Branch created from main@5c52ba2 (current running commit)
- [x] Improve on-demand Discord report: implemented /report/visibility with Markdown tables, summaries, warnings, graph data
- [x] Added /report/visibility + per-node inventory + graph-friendly PG/OSD data
- [x] Documented in README + visibility report markdown sections
- [x] /lxc/reverse-proxy-template already present and documented; leveraged in visibility flows
- [x] Updated with 2026-09-04 probe findings + new visibility implementation notes
- [x] Delivered: /report/visibility returns structured + markdown + raw_graph_data

**Philosophy reminder**: All new work stays read-audit first; write actions remain gated.
