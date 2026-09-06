# Runtime acceptance evidence - 2026-08-31

This record covers local process-level acceptance for the Control API, Edge Gateway startup check,
and Companion API. The latest full run completed at 2026-08-31 12:09 CST (UTC+08:00).

## Command

```bash
.venv/bin/python scripts/local-acceptance.py \
  --component all \
  --report artifacts/runtime/local-acceptance-2026-08-31.json
```

Exit code `0` means every selected contract passed. Exit code `1` means startup, transport, response
status, response shape, security behavior, or a runtime assertion failed. The suite can be restarted
independently with `--component control` or `--component edge`.

## Passed runtime checks

| Component | Executed evidence |
| --- | --- |
| Edge Gateway | `python -m cloudctl_edge --check` returned the exact network-free success payload. |
| Control API health | A real loopback Uvicorn child process returned passing live and ready status in memory repository mode. |
| Control API surface | All 14 required Operations and Debug Session OpenAPI paths were present. |
| Feature alignment | 15 unique catalog modules and 134 unique feature IDs were returned. Policies were 22 `blocked`, 16 `mapped`, and 96 `unmapped`; the local deployment exposed exactly the two built-in revision/snapshot validators. |
| Operations | Create, list, get, cancel, and audit-result completed over HTTP. |
| Approval | A task entered `PENDING_APPROVAL`; self-approval was denied; a different MFA approver released it to `QUEUED`. |
| Debug Session | Create, one-time exchange, get, heartbeat, evidence, and revoke completed. Launch-code replay and a late heartbeat were denied. |
| Companion state | A separate loopback Uvicorn child process completed one-time enroll, device-bound authorization, health upload, and snapshot. |
| Companion actions | Confirmation and emergency stop completed through the mock supervisor and the stopped state returned in the next snapshot. |

The machine-readable report is
`artifacts/runtime/local-acceptance-2026-08-31.json`. It contains no launch code, relay token,
Companion binding token, device certificate, or PEM material.

## Browser live-stack check

At 2026-08-31 12:17 CST, the in-app browser loaded the Web console from port 5173 and Automation
Studio from port 5174 while the development Control API ran on port 8000 in memory repository mode.
The mapped `product-management-09` page displayed `LIVE API`, PDF page 51, the original competitor
route, domain fields, and its four-step workflow. The content-editor role created task
`01a05608-1808-7c2b-bf86-9f3d191c7069` for `works.revision.validate`, rendered its `QUEUED` list row,
and displayed the `operation.task.created` audit event. Fresh Web and Studio tabs contained no browser
warnings or errors; Studio exposed the Python Automation SDK and Monaco workspace while explicitly
remaining disconnected from a real device session.

The machine-readable browser record is
`artifacts/runtime/browser-live-acceptance-2026-08-31.json`. It contains no authentication token,
launch code, certificate, PEM material, or device credential.

## Feature configuration draft live-stack check

At 2026-08-31 21:17 CST, the live Web console and development Control API completed the full
configuration-draft lifecycle for `assets-01`. An initial GET returned `exists=false` and version `0`;
an authorized PUT created version `1`; a subsequent GET restored the saved configuration; and a stale
PUT with `expectedVersion=0` returned `409 CONFLICT`. Viewer reads remained allowed while Viewer writes
returned `403`; a second tenant received an isolated version sequence; and dangerous keys, excessive
depth, and payloads above 64 KiB returned `422`.

The browser then saved a second revision and displayed `后端配置草稿已保存 · v2`. After reload, the page
restored the watermark template, position, opacity, and preview-only flag from the Control API. The
`blocked` feature `collection-01` and `ui_only` feature `system-home-01` both retained draft-save controls
while task creation stayed disabled and the API returned `403`. The audit stream contained
`operation.feature_config_draft.created` without storing sensitive values in this evidence record.

The machine-readable record is
`artifacts/runtime/config-draft-live-acceptance-2026-08-31.json`. It is classified `mock_only` because
the Control API used its in-memory repository and development identity headers; it proves real local
HTTP/browser integration, not production identity, durable database restart, or device execution.

## Android build and authorized device check

Both Android projects were rebuilt from the D-drive workspace with Android 35 and the D-drive Gradle,
SDK, Android-user, and temporary directories. The rebuilt APKs, delivery APKs, and APKs pulled read-only
from device `b0644fb5` had identical sizes and SHA-256 values. Both packages remained installed and
enabled on the OnePlus 9R; launch, UI hierarchy, screenshot, crash/ANR, package, and version checks
passed. DPC ownership remained `no owners`, no provisioning or policy application was performed, and
the unrelated overlay package `com.ydydyd8818` remained enabled.

This hardware evidence proves debug build, debug signing, installation, launch, and read-only UI smoke.
It does not prove production signing, upgrade/rollback, DPC provisioning, or real LAMDA automation.

## Supporting verification

```text
Ruff check scripts/local-acceptance.py: passed
Ruff format --check scripts/local-acceptance.py: passed
Repository-wide pytest: 259 passed
Security boundary script: passed
Committed OpenAPI equality: passed after regeneration
```

`packages/api-contracts/openapi.json` was regenerated after the Operations, Debug Session, authentication,
and executor changes. The committed-contract equality test now matches the live application, and the
repository-wide Python suite passes with 259 tests.

## Evidence classification and residual limits

The local process/browser JSON evidence is deliberately classified as `mock_only`; those reports set
`"hardwareEvidence": false`. Separate Android evidence proves only the explicitly scoped debug-build,
installation, launch, and read-only UI checks described above.

It does not prove:

- Production release signing, APK upgrade/rollback, or managed installation.
- Real Android enrollment, notifications, device-owner provisioning, or work-profile provisioning.
- A real LAMDA connection, authorized device input, screenshot/layout streaming, or evidence upload.
- Edge Hub mTLS connectivity, outage replay, artifact delivery to a device, or long-running soak.
- Browser-to-device behavior through a real Debug Session relay.

Those items require their own software gates or explicitly authorized hardware evidence. Mock
acceptance must never be used to clear a `blocked_hardware` status.
