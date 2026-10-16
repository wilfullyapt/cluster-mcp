#!/bin/bash
set -euo pipefail

# ClusterMCP rename script - run from repo root
# Replaces legacy clustermcp naming with clustermcp / ClusterMCP

echo "Starting ClusterMCP rename..."

# File/directory renames (git mv where possible)
if [ -f references/systemd/clustermcp.service ]; then
  git mv references/systemd/clustermcp.service references/systemd/clustermcp.service || true
fi

# Content replacements (safe, context-aware)
# Core name
find . -type f \( -name "*.py" -o -name "*.md" -o -name "*.toml" -o -name "*.sh" -o -name "*.service" -o -name "*.yaml" \) -exec sed -i \
  -e 's/clustermcp/clustermcp/g' \
  -e 's/ClusterMCP/ClusterMCP/g' \
  -e 's/ClusterMCP Server/ClusterMCP Server/g' \
  -e 's| /opt/clustermcp| /opt/clustermcp|g' \
  {} +

# Service file specific
if [ -f references/systemd/clustermcp.service ]; then
  sed -i 's/clustermcp/clustermcp/g' references/systemd/clustermcp.service
fi

# pyproject.toml package name
if [ -f pyproject.toml ]; then
  sed -i 's/name = "clustermcp"/name = "clustermcp"/' pyproject.toml || true
fi

echo "Rename complete. Review with git diff and git status."
echo "Then: git add -A && git commit -m 'chore: rename clustermcp → clustermcp / ClusterMCP across codebase'"
