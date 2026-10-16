# Wardens Capabilities (Collector + Runner)

**Purpose**: Define exactly what each Warden can see and do so the central MCP can discover, gate, and dispatch accordingly.

**Discovery**: On registration + heartbeat, each node reports its capabilities. MCP stores node → caps mapping and exposes it via API.

## Visibility Capabilities (Collector)

| Capability       | Description                                      | Warden Implementation (C)                          | MCP Endpoint / Storage                  | Discovery Method                  |
|------------------|--------------------------------------------------|----------------------------------------------------|-----------------------------------------|-----------------------------------|
| `lxc:full`       | Full LXC config, mounts, idmaps, resources      | Parse pve config files + /proc/cgroup + pct      | `/wardens/collector/lxc/{node}`        | Capabilities report + heartbeat  |
| `cephfs:mapping` | Subvolumes, host ownership, permissions, quotas | ceph CLI + FS walk + stat calls                   | `/wardens/collector/cephfs/{node}`     | Capabilities report              |
| `docker:status`  | Compose projects, containers, networks, volumes | docker compose inspect + known paths              | `/wardens/collector/docker/{node}`     | Capabilities report              |
| `permissions:audit` | Effective UID/GID, capabilities, path checks | getcap, stat, idmap resolution                    | `/wardens/collector/permissions/{node}`| Capabilities report              |
| `troubleshoot:bundle` | Aggregated diagnostic snapshot                | Combine above + errors + loadavg                  | `/wardens/collector/bundle/{node}`     | Any visibility cap present       |

## Execution Capabilities (Runner – Advanced Tier)

| allowlist_key       | Description                              | Warden Constraints (C)                          | MCP Job Dispatch                          | Discovery                     |
|---------------------|------------------------------------------|------------------------------------------------|-------------------------------------------|-------------------------------|
| `service:restart`   | Restart allow-listed systemd services   | seccomp + cgroups + timeout + audit            | `POST /jobs` with signed payload          | Runner allow-list report     |
| `logs:collect`      | Collect scoped logs / journalctl        | Read-only paths + compression + size limit     | Job result retrieval + audit              | Runner allow-list report     |
| `compose:restart`   | docker compose restart (scoped projects)| Limited to known compose paths                 | Signed job + result                       | Runner allow-list report     |
| `config:safe-read`  | Read-only access to approved configs    | Explicit path allow-list + hash verification   | Job returns content snippet               | Runner allow-list report     |
| `diagnostics:run`   | Pre-approved diagnostic commands        | seccomp + resource limits                      | Job execution + full audit log            | Runner allow-list report     |

## Capability Report Format (sent by Warden on connect)

```json
{
  "node": "pvenodeone",
  "warden_version": "0.1",
  "collector_caps": ["lxc:full", "cephfs:mapping", "docker:status", "permissions:audit"],
  "runner_allowlist": ["service:restart", "logs:collect", "compose:restart"],
  "seccomp_profile": "strict-v1",
  "resource_limits": {"max_mem_mb": 256, "max_cpu_percent": 50, "max_time_s": 300},
  "last_seen": "2026-09-29T..."
}
```

MCP stores this and exposes:
- `GET /wardens/nodes` — list all with caps
- `GET /wardens/nodes/{node}/capabilities`
- `GET /wardens/capabilities` — global view of what is possible

## Additional Cross-Cutting
- `self:update` — signed binary self-update
- `metrics:export` — Prometheus scrape/push
- `audit:stream` — real-time job and visibility audit feed

This structure ensures the MCP always knows exactly what each Warden can provide before requesting data or dispatching jobs.