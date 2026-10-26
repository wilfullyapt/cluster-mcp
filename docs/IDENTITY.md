# ClusterMCP identity

**Status:** package + local path + GitHub slug aligned (2026-10-21).

## Canonical

| Surface | Value |
|---------|--------|
| Display name | ClusterMCP |
| Python package | `clustermcp` (`pyproject.toml`) |
| Seneschal checkout | `/root/seneschal/repos/clustermcp` |
| LXC install path | `/opt/clustermcp` |
| systemd unit | `clustermcp.service` |
| Docker | image tag `clustermcp:test`, compose service `clustermcp`, container `stronghold-clustermcp` |
| GitHub repository | `wilfullyapt/cluster-mcp` |
| git remote `origin` | `https://github.com/wilfullyapt/cluster-mcp.git` (clean HTTPS — never embed PATs) |

Old slug `wilfullyapt/proxmox-mcp` redirects to `cluster-mcp` on GitHub.

## Ownership

- **Code / PR / CI:** Hephaestus
- **Deploy / operate on Stronghold:** Lamassu (Wil gate for production mutate)

## Branch note

Active integration branch: `feature/wardens-integration` (PR #3). Not merged to `main` by agents — Wil reviews / squash-merges.
