# Securing MCP → node SSH (Wardens)

**Threat:** ClusterMCP holds private keys that can reach every enrolled PVE node.

## Model (shipped)

1. **Password once** (`cluster setup`) — full shell only for bootstrap; password never stored.
2. **Forced-command key** — `authorized_keys` installs:
   ```
   from="<optional>",command="/opt/wardens/bin/wardens-ssh-wrapper",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty …
   ```
3. **Wrapper allowlist only**
   - `collect` → run collector
   - `install-binary` → replace collector from stdin
   - `version` → version JSON
   - anything else → denied (no interactive root shell)
4. **Per-node keys** under `$WARDENS_DATA_DIR/ssh/` mode `0700`, private keys `0600`.
5. **Optional source lock:** `WARDENS_SSH_FROM=192.168.0.0/24` (MCP LXC CIDR) baked into `from=`.

## Operator checklist

```bash
# On MCP .env
WARDENS_SSH_FROM=<mcp-lxc-ip-or-cidr>
WARDENS_COLLECT_INTERVAL_SEC=300
FLEET_SYNC_ON_OTA=false

# Re-enroll existing nodes to install wrapper + forced keys (password once each):
cluster setup --ip <node>
```

## Residual risk + next layers (not all shipped)

| Control | Status |
|---------|--------|
| Forced command + session locks | **shipped** |
| `from=` CIDR | **shipped** (env) |
| Per-node keys, no shared fleet key | **shipped** |
| No password at rest | **shipped** |
| Encrypt private keys at rest (age/sops/TPM) | planned |
| SSH CA short-lived host certs | planned |
| Dedicated non-root warden user + capabilities | planned |
| Signed install-binary payloads | planned |
| Audit log of every collect/update | partial (MCP logs) |

**Bottom line:** MCP can still *reach* nodes, but the key is not a general root login — only Wardens ops. Compromise of MCP is still serious; treat the LXC as high-trust, keep API key on, restrict network to management VLAN.
