# P1-005 evidence summary

- Task: Content, revision, group domain and API
- Audited: 2026-08-31
- Software status: `implemented`
- Acceptance status: `pending`

## Implemented closure

- Content creation persists an immutable first revision with a canonical payload digest.
- New revisions receive monotonically increasing revision numbers and immutable payload hashes.
- Tenant-scoped content groups support unique names and idempotent membership creation.
- Content listing exposes the latest revision and current group membership.
- Archiving is audited, idempotent, and prevents later revision creation.

## Verification

- HTTP integration covers content creation, second revision, group creation, membership add/remove, listing, archive, and post-archive rejection.
- The combined authorization and integration suite passed 36 tests.
- The repository Python suite passed 159 tests after these changes.

## Remaining external gates

Acceptance remains pending until production persistence, backup/restore, and the web content workflows are exercised against a deployed control plane.
