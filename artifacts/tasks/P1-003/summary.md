# P1-003 evidence summary

- Task: Account authorization and device binding model
- Audited: 2026-08-31
- Software status: `implemented`
- Acceptance status: `pending`

## Implemented closure

- Tenant-scoped platform accounts retain an approved secret-store reference instead of credential material.
- Account authorization has explicit expiry, health status, suspension, and revocation state.
- Authorized accounts can be bound and unbound from tenant-owned devices with an operator confirmation record.
- Suspending or revoking an account removes active bindings and prevents further binding until authorization is restored.
- Responses expose `secretConfigured` without returning the secret reference, while audit records hash sensitive references.
- Publish-plan validation requires an active account-to-device binding for the selected target.

## Verification

- Account creation, duplicate rejection, binding, unbinding, suspension, secret redaction, and suspended-binding rejection pass through the HTTP API.
- The combined authorization and integration suite passed 36 tests.
- The repository Python suite passed 159 tests after these changes.

## Remaining external gates

Acceptance remains pending until a production platform adapter validates credential health and account ownership against an authorized external test account.
