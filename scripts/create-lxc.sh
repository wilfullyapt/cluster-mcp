#!/usr/bin/env bash
# Stronghold ClusterMCP — LXC deployment helper
# Run on pve-01 (or any node) as root.
# This is a starting point — review and customize storage/network before running.

set -euo pipefail

CTID=210          # Choose an unused CTID
HOSTNAME=clustermcp
STORAGE=local-lvm # or local-zfs, cephfs, etc.
BRIDGE=vmbr0
IP="YOUR_LAN_IP/24"   # Static IP — adjust to your LAN
GATEWAY="YOUR_GATEWAY"

echo "Creating Debian 12 LXC for ClusterMCP Server (CTID $CTID)..."

# Download template if needed (Debian 12)
pveam update || true
pveam download local debian-12-standard_12.7-1_amd64.tar.zst || true

pct create $CTID local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
  --hostname $HOSTNAME \
  --storage $STORAGE \
  --net0 name=eth0,bridge=$BRIDGE,ip=$IP,gw=$GATEWAY \
  --cores 1 \
  --memory 512 \
  --unprivileged 1 \
  --features nesting=1 \
  --rootfs $STORAGE:8

pct start $CTID
sleep 5

echo "LXC created. Now SSH or pct enter $CTID and run the setup steps in README.md"
echo "After setup, the MCP will be available at http://$IP:8000"