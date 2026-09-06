# P1-004 evidence summary

- Task: S3 media upload, hashing, and derivative pipeline
- Audited: 2026-08-31
- Software status: `implemented`
- Acceptance status: `pending`

## Implemented closure

- The control plane exposes checksum-bound upload authorization through an object-store port.
- Production configuration requires S3 mode, credentials, and HTTPS for an explicitly configured endpoint.
- Upload completion verifies object existence, size, content type, and SHA-256 before registering an asset.
- Asset registration is idempotent by tenant and digest.
- Derivative requests are persisted and emitted through the outbox; terminal results require a traceable source/output relationship.
- Tests inject the in-memory object-store implementation without weakening production S3 validation.

## Verification

- HTTP integration covers upload authorization, object insertion, checksum verification, idempotent completion, derivative request/result, and checksum rejection.
- The combined authorization and integration suite passed 36 tests.
- The repository Python suite passed 159 tests after these changes.

## Remaining external gates

Acceptance remains pending until the production S3-compatible service, retention policy, and deployed derivative worker are exercised with authorized media.
