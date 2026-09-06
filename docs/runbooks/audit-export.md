# Audit export

Only a role with `audit.read` may call `/api/v1/audit-events`. Export with a short-lived bearer
token supplied through an environment variable, never a command-line argument or URL:

```bash
export CLOUDCTL_AUDIT_EXPORT_TOKEN='issued-by-approved-identity-provider'
.venv/bin/python scripts/export-audit.py \
  --base-url https://control-api.example.com \
  --output secure-evidence/audit-20260831.json
```

The tool rejects credential-bearing URLs, redirects, non-HTTPS remote origins, oversized or
non-JSON responses, and multi-tenant payloads. It redacts known credential/PEM fields, writes the
bundle and checksum atomically with mode `0600`, and never prints the token.

Store the result in the approved immutable evidence system with its authorization ticket,
retention class, legal hold state, requester, tenant, request/correlation identifiers, and SHA-256.
Test the export against production identity/RBAC and object retention controls before declaring
P5-005 complete.
