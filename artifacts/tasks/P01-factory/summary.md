# P01 T077 command factory

Date: 2026-09-08

## What changed

`cloudctl_api.command_factory` maps the 31 xy-tasks field-map entries (plus
Xiaohongshu `red-tasks-01` and `device-probe`) to typed CommandV1 parameters.

- Unknown / forbidden fields fail closed
- `AVAILABILITY_PENDING` and unwired catalog commands cannot mint
- `xy-tasks-01` aliases to `xianyu.publish_listing.v1` and stays OPEN_ONLY
- `POST /api/v1/platform-tasks` accepts `operationId` and fills `commandType`

Recipes are still not required. This does not enable polish/delete/charge.

## Tests

`pytest tests/unit/test_command_factory.py tests/integration/test_platform_tasks.py` — 20 passed

## Live

Factory files copied onto Seoul `20260901-1800` and `cloudctl-mobile-api` restarted.
`xy-tasks-03` (擦亮) returned 422. `operationId=device-probe` minted `ca985a89-6b54-45d8-9511-914be99a60de` and succeeded (`controlEpoch` 94, `DeviceProbeResult`). No 闲鱼 publish task was created.
