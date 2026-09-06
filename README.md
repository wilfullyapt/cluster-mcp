# Stronghold Proxmox MCP Server

Self-contained, repeatable-tools server for Hermes butler access to Proxmox cluster, VMs/LXCs, Ceph, network inventory, tasks, and health snapshots.

**Philosophy**
- MCP = repeatable queries and status tools (Ceph health, cluster overview, IP inventory, recent tasks, aggregated snapshots).
- Finite/one-off work (new VM/LXC creation, interactive setup) stays on the SSH path.
- Dogfood for Stronghold → extractable OpenKEEP template.

## Quick Deploy (LXC Recommended — Current Setup)

The service is currently running at **http://YOUR_MCP_LXC_IP:8000** in a dedicated LXC (CTID of your choice).

### 1. On PVE node (create or update LXC)
Use or adapt `scripts/create-lxc.sh` (update IP to YOUR_MCP_LXC_IP/24, CTID, storage, bridge as needed). Current LXC was manually provisioned.

### 2. Inside the LXC (YOUR_MCP_LXC_IP)
```bash
# Install deps
apt update && apt install -y python3 python3-venv python3-pip git curl

# Clone (after repo is public/pushed)
git clone https://github.com/wilfullyapt/proxmox-mcp.git /opt/proxmox-mcp
cd /opt/proxmox-mcp

# Setup
cp .env.example .env
# Edit .env with real PVE_HOST (https://YOUR_PVE_HOST:8006), TOKEN_ID, TOKEN_SECRET (from pveum)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Run (dev)
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

### 3. Production: systemd for Auto-Start + Auto-Recovery
See `references/systemd-unit.md` for the unit file.

```bash
# Copy and enable
sudo cp references/systemd-unit.md /etc/systemd/system/proxmox-mcp.service
# (or paste the [Unit] content directly)
sudo systemctl daemon-reload
sudo systemctl enable --now proxmox-mcp
sudo systemctl status proxmox-mcp
journalctl -u proxmox-mcp -f
```

`Restart=always` ensures recovery on crash or reboot.

### 4. Proxmox Token & Permissions (Wil is fixing)
See `references/permissions-cheatsheet.md` for exact `pveum` commands.

Minimal role + ACL at `/` is required for cluster-wide endpoints. Current token lacks these → 403s.

### One-Line Update Command
After initial clone and service setup:

```bash
cd /opt/proxmox-mcp && ./scripts/update.sh
```

Or directly:
```bash
cd /opt/proxmox-mcp && git pull && sudo systemctl restart proxmox-mcp
```

This pulls latest, rebuilds if Docker, or restarts the systemd service. Run inside the LXC.

### Docker Alternative (in LXC or elsewhere)
```bash
cp .env.example .env  # edit with secrets
docker compose up -d --build
# Update: docker compose up -d --build
```

## Endpoints (v0.5 – Visibility & Admin Focus)
- `GET /health`
- `GET /cluster/status`
- `GET /nodes`
- `GET /ceph/status`
- `GET /ceph/osds`
- `GET /resources?type=vm|container|storage`
- `GET /tasks/recent`
- `GET /health/snapshot` ← aggregated report
- `GET /report/visibility` ← rich per-node inventory, Ceph PG/OSD health, warnings, Markdown sections + graph-friendly data for Discord/Hermes
- `POST /admin/update` (self-update endpoint for autonomous maintenance)
- `POST /vm/{node}/{vmid}/status/{start|stop|reboot|shutdown}` (gated)

All return `ActionResponse {success, data, error}`. PVE calls use the configured token.


## Visibility Reports (feature/stronghold-mcp-visibility-report)

**`/report/visibility`** returns rich aggregated data optimized for Discord embeds and Hermes digests:

- Per-node inventory (status, CPU/mem, VM/CT counts, uptime)
- Resource summary by type
- Ceph health + PG state counts (graph data)
- OSD summary (up/down/in/out)
- Actionable warnings list
- Pre-formatted Markdown tables/sections for immediate posting
- Raw graph payloads (pg_states, node metrics)

Example usage in Hermes: call and render the `markdown` or `summary` sections.

**Full Working Surface (current endpoints + privs)**:
- `/health`, `/cluster/status`, `/nodes`, `/resources`, `/ceph/status`, `/ceph/osds`, `/tasks/recent`, `/health/snapshot`, `/report/visibility`: Read (Sys.Audit, Datastore.Audit, etc.)
- `/lxc/create`, `/lxc/exec` (gated with confirm): Write (VM.Allocate, etc.) — use with care
- `/admin/update`: Protected by MCP_API_KEY; triggers git pull + restart
- `/lxc/reverse-proxy-template`: Returns Caddy-ready LXC template (leverage for reverse proxy setups)
- Capabilities mapping available via planned /capabilities once ACLs permit

**Recommended PVE token privs**: See references/permissions-cheatsheet.md (Sys.Audit, Datastore.Audit, VM.Monitor, etc. for read-heavy ops).

Flows: Status queries → visibility report → Discord digest. Write actions always require explicit confirm + role checks.


## Auto-Update on Push (Future / Optional)
- GitHub webhook → LXC deploy hook (simple HTTP endpoint that validates secret and runs update.sh).
- Or GitHub Actions: on push to main → ssh to LXC (deploy key) → run update command.
- Current: one-line command above (reliable, no extra services).

## Integration with Hermes
- Add `YOUR_MCP_LXC_IP:8000` to network reachability.
- Future skill will expose endpoints as tools.
- All calls logged on MCP side for audit.

## Development
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

## License
MIT — see LICENSE. This component is the Stronghold dogfood for the public OpenKEEP template.

## References
- `references/permissions-cheatsheet.md`
- `references/systemd-unit.md`
- `scripts/create-lxc.sh`
- `scripts/update.sh` (one-line helper)

## Usage Examples & Answers

### LXC + Docker Registry + Gitea
Yes, the MCP can create an LXC and run post-creation commands via /lxc/exec (with confirm=true).

Example flow:
1. Create LXC with /lxc/create
2. Install Docker + run Gitea/Registry containers using /lxc/exec

### Ceph Support
Yes - /ceph/status and /ceph/osds are available. More Ceph tools are planned (see TODO.md).

## Testing
Run: pytest --cov=.


## Admin Endpoints (Self-Maintenance)

**POST /admin/update**
- Body: `{"ref": "origin/main", "force": false, "dry_run": false}`
- Requires `X-API-Key` header when `MCP_API_KEY` is set in env.
- Triggers git update + pip install + service restart.
- Use with caution; the service will restart.

Example:
```bash
curl -X POST http://mcp-ip:8000/admin/update \
  -H "X-API-Key: yourkey" \
  -H "Content-Type: application/json" \
  -d '{"ref": "origin/main"}'
```

After calling, poll `/health` or `/admin/update/status`.
