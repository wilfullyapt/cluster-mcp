#!/bin/bash
# Historical one-shot helper used during the proxmox-mcp → ClusterMCP rename.
# The rename is already applied on this branch; keep this script as a no-op
# marker so old docs/runbooks that call it do not fail loudly.
set -euo pipefail

echo "ClusterMCP rename already applied in-tree."
echo "Package name: clustermcp (see pyproject.toml)"
echo "Service unit: references/systemd/clustermcp.service"
echo "CI image tag: clustermcp:test"
echo "Nothing to do."
exit 0
