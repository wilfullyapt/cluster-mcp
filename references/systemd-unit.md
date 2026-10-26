# systemd Unit for ClusterMCP (LXC Production)

## Unit File: /etc/systemd/system/clustermcp.service

```ini
[Unit]
Description=Stronghold ClusterMCP Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/clustermcp
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/clustermcp/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## Setup in LXC

```bash
# After cloning to /opt/clustermcp and setting up venv + .env
sudo cp references/systemd-unit.md /etc/systemd/system/clustermcp.service  # or copy the ini content
sudo systemctl daemon-reload
sudo systemctl enable --now clustermcp
sudo systemctl status clustermcp
```

## Auto-recovery & Update

- `Restart=always` handles crashes/reboots.
- For code update (one-line):
  ```bash
  cd /opt/clustermcp && git pull && sudo systemctl restart clustermcp
  ```
- Or use the helper script (see README).

## Logging

```bash
journalctl -u clustermcp -f
```

## Health Monitoring (optional)

Add a simple watcher or integrate with hermes-monitor for `/health` pings and alerts on failure.