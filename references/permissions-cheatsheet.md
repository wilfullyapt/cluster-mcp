# ClusterMCP Token Permissions Cheatsheet

## Recommended Minimal Role (PVEAuditor-like)

Create a custom role via GUI or CLI:

```bash
pveum role add PVEAuditorMCP --privs "Sys.Audit Datastore.Audit SDN.Audit VM.Audit VM.Monitor Ceph.Audit Permissions.Read"
```

## Token Creation

```bash
# Create user if needed (or use existing)
pveum user add hermes@pam --comment "Hermes MCP service account"

# Create token (note the ! separator)
pveum user token add hermes@pam hermes-mcp --privsep 0
# Output includes secret — save it securely in .env only
```

## ACL Assignment (Critical — apply at root)

```bash
# Apply the role at datacenter root (/) so cluster-wide endpoints work
pveum acl modify / --token 'hermes@pam!hermes-mcp' --role PVEAuditorMCP
```

## Verification

```bash
pveum user token permissions hermes@pam hermes-mcp
pveum acl list | grep hermes-mcp
```

Test with MCP `/health/snapshot` or direct curl to PVE API.

## Notes
- Never grant full Administrator or PVEAdmin.
- Token has no privileges until explicit ACL at `/`.
- For power actions (optional), add `VM.PowerMgmt` to role.
- All MCP calls are logged on the server for audit.