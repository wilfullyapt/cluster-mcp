#!/usr/bin/env bash
# One-line update helper for ClusterMCP (run inside LXC or Docker host)
# Usage: ./scripts/update.sh   or   make update

set -euo pipefail

echo "Updating ClusterMCP from git..."
git fetch origin
git reset --hard origin/main

if [ -f docker-compose.yml ]; then
    echo "Docker mode detected — rebuilding and restarting..."
    docker compose pull || true
    docker compose up -d --build
else
    echo "Native/LXC mode — restarting systemd service..."
    sudo systemctl restart clustermcp || echo "systemd not found, try uvicorn manually or install service"
fi

echo "Update complete. Check status with: curl http://localhost:8000/health or journalctl -u clustermcp"
