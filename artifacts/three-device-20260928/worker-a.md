# Work Package 1A Evidence

- Date: 2026-09-28
- Work item: 1A, read-only three-device ADB preflight
- Baseline: `80171144e3032cfac80924151a7d76839b9a20b5`
- Branch: `agent/sol-preflight-20260928`
- Delivery commit: this evidence file's commit (resolve from the delivered branch tip)
- Frozen execution plan: `docs/current/three-device-execution-20260928.md`

## Implemented scope

- Requires exactly three unique, explicit, repeated `--serial` values; it never selects a device.
- Uses only bounded, fixed-argv reads: `adb devices`, allowlisted `getprop`,
  `dumpsys package`, filtered `pm list packages -d`, `pidof`, and
  `dumpsys accessibility`.
- Emits a JSON whitelist containing requested serials, safe device properties,
  parsed package/version/status, process state, accessibility evidence, and
  readiness reason codes. It emits no raw command output, stderr, UI, account,
  credential, or unrequested-device data.
- Separates ADB authorization, local runtime prerequisites, and cloud/account
  readiness. Cloud/account readiness is always `UNKNOWN_NOT_CHECKED`; local
  unknown or ambiguous evidence fails closed.
- Accepts a bound accessibility service only when the expected full component
  identity is present. A CloudCtl-like label without the component is reported
  as `AMBIGUOUS_LABEL_ONLY`, not as bound.
- Performs no mutation, uses no shell, and makes no hardware or business
  acceptance claim.

## Verification

All commands ran in `/private/tmp/cloudctl-sol-preflight-20260928` with the
shared read-only Python executable.

| Command | Exit | Result |
| --- | ---: | --- |
| `/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/python -m pytest -q tests/ops/test_three_device_preflight.py` | 0 | 24 passed in 0.03s |
| `/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/python -m ruff check scripts/three_device_preflight.py tests/ops/test_three_device_preflight.py` | 0 | All checks passed |
| `/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/python -m ruff format --check scripts/three_device_preflight.py tests/ops/test_three_device_preflight.py` | 0 | 2 files already formatted |
| `/Users/wangziheng/Desktop/01-主战场/LAMDA云控系统/cloudctl-source/.venv/bin/python scripts/three_device_preflight.py --help` | 0 | Help rendered; no ADB command executed |
| `git diff --check` | 0 | No whitespace errors |

Tests use mocked subprocess execution only. No ADB, SSH, network, production,
APK installation, deployment, or real-device operation was performed.

## Residual gaps

- The controller must run any real-device diagnostic under the declared device
  locks and retain only the structured JSON result.
- Version values are observed, not interpreted as a compatibility policy;
  acceptance-version unification remains phase 2 work.
- Tenant binding, account login, cloud enrollment, tasks, leases, and production
  readiness are outside this CLI and remain unverified.
- Label-only bound-service output cannot prove component identity. A device with
  only that evidence remains unknown until a definitive component identity is
  available through an authorized read or local application evidence.
