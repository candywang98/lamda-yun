# Legacy Order Projection Guard / 20260928.1

Scope: close the legacy screen upload regression documented by
`order-delivery-20260926.md`; no wire schema or database migration.

1. A legacy screen upload must not create or change a current order projection
   for a key already protected by `OrderDeliveryProjectionRow` in the same
   tenant, device and platform. Key normalization matches the existing upsert.
2. A new legacy page containing any protected key is rejected atomically with
   HTTP 409 / `ORDER_DELIVERY_PROTOCOL_REQUIRED`. No order, page, checkpoint,
   projection watermark or durable receipt changes survive the rejection.
3. Exact replay of an already accepted legacy page may retain its existing
   read-only replay ACK. It must not mutate projections or regress checkpoints.
4. Unprotected legacy-only rows retain existing compatibility. Keys in another
   tenant or device do not trigger the guard or disclose their existence.
5. Legacy and durable screen admissions serialize on the same device row on
   databases supporting row locks. If legacy wins first, a later durable write
   may establish its projection. If durable wins first, legacy fails closed.
   SQLite tests alone do not prove concurrent PostgreSQL locking behavior.
6. The guard belongs in legacy admission, before checkpoint/page side effects.
   Durable `_upsert_observed_orders` remains the owner of generation ordering.
   No client-controlled bypass, disabling of identity checks, or new broad
   upload route is introduced.
7. This does not solve equal composite order-key collisions, historical
   account attribution, or arbitrary account switching. Those remain separate
   contracts and acceptance gates.

Required regression cases: stale legacy status against a protected order;
mixed protected/unprotected rows with complete rollback; protected missing
fields; replay of an existing legacy page; other-tenant/device equal key;
unprotected legacy compatibility; durable generation ordering retained.
Exercise PostgreSQL serialization in a disposable test database when available;
otherwise state the unverified concurrency gap explicitly.
