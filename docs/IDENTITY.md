# ClusterMCP identity

**Status:** local + package rename complete (2026-10-21, Synapse `t_c3d33c0f`).

## Canonical

| Surface | Value |
|---------|--------|
| Display name | ClusterMCP |
| Python package | `clustermcp` (`pyproject.toml`) |
| Seneschal checkout | `/root/seneschal/repos/clustermcp` |
| LXC install path | `/opt/clustermcp` |
| systemd unit | `clustermcp.service` |
| Docker | image tag `clustermcp:test`, compose service `clustermcp`, container `stronghold-clustermcp` |

## Dual name (intentional)

| Surface | Value | Why |
|---------|--------|-----|
| GitHub repository slug | `wilfullyapt/proxmox-mcp` | No GitHub write auth on seneschal host this run; Wil-owned rename when ready |
| git remote `origin` | `https://github.com/wilfullyapt/proxmox-mcp.git` | Clean HTTPS only — never embed PATs |

After Wil renames the GitHub repo to `clustermcp` (or similar):

1. Confirm GitHub auto-redirect from old slug.
2. `git remote set-url origin https://github.com/wilfullyapt/clustermcp.git` (clean HTTPS/SSH).
3. Update Reliquary shipyard + stronghold pointers.
4. Drop dual-name notes from this file and README Identity section.

## Ownership

- **Code / PR / CI:** Hephaestus
- **Deploy / operate on Stronghold:** Lamassu (Wil gate for production mutate)

## Branch note

Active integration branch: `feature/wardens-integration` (includes in-tree rename + wardens nest). Not merged to `main` by agents — Wil reviews.
