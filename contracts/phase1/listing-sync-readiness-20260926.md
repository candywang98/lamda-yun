# Listing Sync Readiness, listing-sync/20260926.1

Controller-frozen delta on `f0c3e4b`. Preserve receive-only boundaries.
No real device operations, publishing, delisting, or task creation during tests.

## Ownership

- Controller: `fleet_listings.py`, backend tests, generated OpenAPI, current plan
  and evidence. No database migration or existing message/identity rewrite.
- Web worker: `ListingInfoCollectView.vue`, `features/fleet/listings-api.ts`,
  focused listing collection tests, and a small listing-specific helper only
  where needed. Do not change shared scheduling or other operation pages.

## Additive History DTO

GET `/api/v1/fleet/listings/history` keeps its existing envelope, filters and
cursor. Each item additionally returns `id` (existing row UUID), `deviceId`,
and `platform`. Device/tenant separation remains unchanged. Sort ties use
last_seen_at DESC, item_key ASC, id ASC. No fabricated platform ID.

The frontend displays the source device and uses row id as its key; for older
DTOs without these fields, show an unknown source and a collision-safe fallback,
never infer a device or collapse rows with the same itemKey.

## Operator Collection

Existing collect executor is already wired; do not rebuild it.
For immediate collection:

- Generate a fresh idempotency identity for each explicitly new collection.
  Same-day repeated successful collections must produce independent tasks.
- Disable duplicate submissions while a batch is pending.
- Snapshot selected devices. Show per-device success/failure and task IDs.
  Partial/ambiguous failures retry only unresolved devices with the SAME
  idempotency keys; successful devices are not redispatched.
- Missing/malformed task ID is a failure, never a successful empty task.
- Respect device.control in the page as well as existing backend enforcement.
- This page currently ignores the shared scheduling editor. Remove the
  unimplemented once/recurring choices rather than silently dispatching now.
  Do not implement a second scheduler or broaden cloud scheduling in this delta.
- Listing history supports visible loading/error/empty states, refresh,
  per-device filtering and existing cursor pagination. Reject stale responses.
  Refresh never itself creates or retries a phone task.

## Verification

Backend: additive IDs/device/platform, same-key different devices, tenant
isolation, stable tie pagination; preserve existing ingest/history tests.
Web: independent repeated collections, double-click protection, partial
failure retry, ambiguous/malformed responses, permissions, actual selected
device snapshot, source display, legacy DTO safety, history paging/error/races,
and no ignored scheduling controls. No browser space18 takeover.
