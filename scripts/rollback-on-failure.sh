#!/bin/bash
# rollback-on-failure.sh
# Called from systemd ExecStopPost or a health watcher.
# Rolls back to LAST_KNOWN_GOOD commit if the service fails to become healthy.

set -euo pipefail

REPO_ROOT="${MCP_REPO_ROOT:-/opt/proxmox-mcp}"
LAST_GOOD_FILE="$REPO_ROOT/.last-known-good"
HEALTH_URL="http://127.0.0.1:8000/health"
MAX_ATTEMPTS=5
SLEEP=3

cd "$REPO_ROOT"

if [[ ! -f "$LAST_GOOD_FILE" ]]; then
    echo "No last-known-good marker. Skipping rollback."
    exit 0
fi

LAST_GOOD=$(cat "$LAST_GOOD_FILE")

echo "Checking health after update..."
for i in $(seq 1 $MAX_ATTEMPTS); do
    if curl -sf "$HEALTH_URL" > /dev/null; then
        echo "Health check passed. Update successful."
        exit 0
    fi
    echo "Attempt $i/$MAX_ATTEMPTS failed. Waiting..."
    sleep $SLEEP
done

echo "Health check failed after update. Rolling back to $LAST_GOOD"
git reset --hard "$LAST_GOOD"
git clean -fd
systemctl restart proxmox-mcp || true
echo "Rollback completed."
exit 1
