# Install Wardens via ClusterMCP (`cluster setup`)

**Model:** ClusterMCP is the control plane. Wardens are a **bridge binary** on each
Proxmox node. The bridge does **not** know where MCP lives and never calls home.
Interval collection and runs are initiated by MCP.

**Who:** Hephaestus builds artifacts; operators (Lamassu) run `cluster setup` from
the MCP host (or any host with the enrolled key store).

## Prerequisites

- ClusterMCP checkout with deps (`pip install -r requirements.txt`)
- Built collector: `make -C wardens/build collector`
- Network path from MCP host → node SSH (port 22)
- One-time root (or sudo-capable) password on the node — **never stored**

## Build bridge binary

```bash
cd /path/to/clustermcp
make -C wardens/build clean && make -C wardens/build collector
export WARDENS_COLLECTOR_BIN="$PWD/wardens/build/collector"   # optional if default path
```

## Enroll a node

On the MCP host:

```bash
# Interactive password prompt (not echoed, not saved)
cluster setup --ip 192.168.0.10

# Or pipe once:
printf '%s\n' "$NODE_PASSWORD" | cluster setup --ip 192.168.0.10 --password-stdin
# or: CLUSTER_SETUP_PASSWORD=... cluster setup --ip 192.168.0.10
# (env var is popped during setup; still never written to inventory)
```

What setup does:

1. SSH with the provided password (ephemeral)
2. Checks host is Proxmox (`/etc/pve`, `pveversion`)
3. Generates an ed25519 key pair under `$WARDENS_DATA_DIR/ssh/` (default `/var/lib/clustermcp/wardens/ssh/`)
4. Installs the public key on the node
5. Installs `/opt/wardens/bin/wardens-collector` + `/etc/wardens/collector.env` (**node name only** — no MCP URL)
6. Writes enrollment record under `$WARDENS_DATA_DIR/nodes/` (**no password field**)

## MCP-initiated collect

```bash
cluster collect --node pvenodeone
# or HTTP:
curl -sS -X POST http://127.0.0.1:8000/wardens/nodes/pvenodeone/collect | jq .
curl -sS http://127.0.0.1:8000/wardens/nodes/pvenodeone/report | jq .
curl -sS http://127.0.0.1:8000/wardens/enrolled | jq .
```

Scheduling (interval) belongs on the MCP side (cron / systemd timer calling
`cluster collect` or `POST .../collect`) — **not** a timer on the node.

## Bridge contract

- Env: `WARDEN_NODE` (required), `WARDEN_VERSION` (optional)
- stdout: one `CollectorReport` JSON document
- stderr: diagnostics
- No outbound HTTP

## Runner

Do **not** enable runner. Skeleton only.

## Rollback on a node

```bash
rm -f /root/.ssh/authorized_keys   # only remove the clustermcp-* line in practice
rm -rf /opt/wardens /etc/wardens
# On MCP: delete $WARDENS_DATA_DIR/nodes/<node>.json and ssh/warden-<node>*
```
