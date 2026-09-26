# OnePlus V3 Connected Read-Only Verification

## Scope

The user explicitly requested testing while the cable remains connected and
fixing defects iteratively. USB disconnection is a final independent-operation
acceptance condition, not a prerequisite for every development test.

Cloud was idle at preflight, but OnePlus's last request was approximately seven
minutes old. With exact-serial device lock fencing12, the controller performed
one diagnostic `adb shell am start` of Companion MainActivity. Screen was Awake.
This restored a fresh connection. No ADB business navigation, tap, swipe, input,
screenshot, force-stop or installation was used in this turn.

Both business tasks were created using normal operator authentication through
`POST /api/v1/xianyu/orders:collect`. Companion v3 executed the existing
read-only SOLD workflow. The cable remained connected: these results are
**connected diagnostic evidence, not final ADB-disconnected acceptance**.

## Results

All times below are UTC on 2026-09-26.

| Case | Run / Task | Result |
| --- | --- | --- |
| Single screen, maxRows10 | run `0adcb6e3-e4d0-5167-93f7-cf3b07b8d509`; task `b067fca9-7ffa-49df-85b0-6c812fe4179c` | Created 16:55:18; observed SUCCEEDED/SYNCED 16:55:56; 1 SCREEN + COMPLETE; 3 distinct captured snapshots; zero partial rows |
| Three screens, maxRows10 per screen | run `8ffc9121-00c1-561e-b57b-59c4d887c4e7`; task `5906545b-e755-4343-8ad9-a1db2d2bd3a5` | Created 16:59:51; observed SUCCEEDED/SYNCED 17:00:23; SCREENs 1/2/3 + COMPLETE; 10 distinct captured snapshots; zero partial rows |
| Exact request-key replay of three-screen run | Same run and task | At 17:01:51, HTTP200, Idempotency-Replayed=true, same task identity, delivery still SYNCED; no new tasks, orders, receipts or content changes |

No second manual launch was needed before the three-screen run: cloud preflight
at 16:59:28 saw an authenticated OnePlus request at 16:59:27.938805.
This bounded observation is not a long-term background endurance result.

For both completed runs:

- SCREEN/COMPLETE payload hashes match their receipt SHA256 values.
- No receipt conflict; run identity and direction match.
- Screen ordinals are contiguous and match the accepted completion count.
- Each captured key exists in the device's SOLD order data.
- Normal Web list/detail APIs return the matching device/order identities;
  returned title, counterparty, amount and status match database projections.
- All captured orders were found on the first device-filtered API page.
- Stop reason is PLAN_FINISHED, not a fabricated empty-page completion.

The first run's device-filtered SOLD API total was 7; after three screens it was
11. The three-screen run observed 10 of those order snapshots, not a proof that
the entire account history was collected. Across directions, the device had 14
stored orders. The idempotency check compared the complete content digest of
those 14 rows and all four receipts, with no change.

## Important Identity Limitation

All captured keys use the existing composite format
`SOLD|counterparty|title|amount`, not a platform order number.
Ten distinct keys do not prove perfect identity separation for separate orders
with identical counterparty/title/amount. That existing limitation and the
deferred historical account partition must not be represented as solved by this
transport test.

## Cleanup And Remaining Work

- Cloud tasks 377 -> 379, exactly the two authorized read-only tasks.
- Request replay created zero tasks.
- Outgoing messages stayed 23.
- Cloud idle checks passed after completion and replay.
- Device lock fencing12 released `2026-09-26T17:02:29Z`.
- No maintenance change, message send, publishing, delisting, shipping, review
  or trading action. Neither Huawei was operated.
- No phone content, names, prices or raw screenshots are committed to evidence.
- Existing browser space18 remains with the user; Web API correctness was
  checked, not browser visual rendering.

Remaining: visual page acceptance, real interruption/recovery, existing two
Huawei integrations, final independent-operation acceptance, and the separately
recorded identity/history/legacy-channel gaps. Continue development while
connected; do not request disconnection for every iteration. O10 remains
IN_PROGRESS / DEVICE_WAIT overall.

Evidence: `v3-connected-progress.jsonl`, `v3-connected-verification.json`,
`v3-connected-pages-progress.jsonl`, `v3-connected-pages-verification.json`,
`v3-connected-replay.json`.
