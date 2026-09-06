# Incident response

## Device write conflict

1. Put the device into maintenance and stop new scheduling.
2. Compare the database lease, Edge maximum fencing token, active runner, and LAMDA lock owner.
3. Never lower or reuse a fencing token. Expire the old lease and issue a new monotonically increasing token.
4. Preserve Edge spool, task events, UI dumps, screenshots, and workflow identifiers for audit.
5. Reconcile any target that reached `COMMITTING`; do not resubmit an uncertain commit.

## Suspected credential exposure

1. Revoke the affected Edge or signing certificate and disconnect its stream.
2. Rotate the credential through the approved secret system. Do not send PEM material through the Web UI.
3. Search structured logs by fingerprint and request ID, not by raw secret value.
4. Verify production and laboratory trust roots remain separated.

