# Install Wardens collector on a Proxmox node (lab)

**What this is:** a host-local **node agent** (systemd + binary), not a PVE UI add-on.

**Who:** Hephaestus builds artifacts; **Lamassu** deploys/operates on Stronghold nodes.

## Prerequisites

- Proxmox VE host (reads `/etc/pve/lxc`)
- ClusterMCP reachable on the LAN (e.g. LXC running uvicorn on port 8000)
- Build host with: `gcc`, `make`, `libcurl` dev headers  
  Debian/PVE: `apt install build-essential libcurl4-openssl-dev`

## Build (from ClusterMCP checkout)

```bash
cd /path/to/clustermcp/wardens/build
make clean && make collector
# optional static musl:
# make clean && make STATIC=1 CC=musl-gcc collector
ls -la collector
```

## Install on node

```bash
install -d /opt/wardens/bin /etc/wardens
install -m 755 collector /opt/wardens/bin/wardens-collector
```

### Environment file `/etc/wardens/collector.env`

```bash
WARDEN_NODE=pvenodeone
CLUSTERMCP_URL=http://192.168.0.233:8000
# MCP_API_KEY=...   # if ClusterMCP has MCP_API_KEY set
WARDEN_VERSION=0.2.0
```

### systemd oneshot + timer (recommended for MVP)

Unit: `references` in-repo → copy from checkout:

- `wardens/docs/systemd/wardens-collector.service`
- `wardens/docs/systemd/wardens-collector.timer`

```bash
cp wardens/docs/systemd/wardens-collector.service /etc/systemd/system/
cp wardens/docs/systemd/wardens-collector.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now wardens-collector.timer
systemctl start wardens-collector.service   # run once now
journalctl -u wardens-collector -n 50 --no-pager
```

## Verify against ClusterMCP

```bash
curl -sS "$CLUSTERMCP_URL/wardens/nodes" | jq .
curl -sS "$CLUSTERMCP_URL/wardens/nodes/${WARDEN_NODE}/report" | jq .
curl -sS "$CLUSTERMCP_URL/wardens/reports" | jq .
```

## Runner

Do **not** install/enable `runner` for lab MVP. It is a non-functional skeleton.

## Rollback

```bash
systemctl disable --now wardens-collector.timer wardens-collector.service
rm -f /etc/systemd/system/wardens-collector.*
systemctl daemon-reload
rm -rf /opt/wardens /etc/wardens
```
