# Worker v6 device recovery gate

## Scope

- Branch: `agent/sol-v6-recovery-20260928`.
- Baseline: `e205e43f312070f21ca4290b452279511aad0cc4`.
- Candidate source: `9c98c5f364d39be10cdb9ab903552dde77f4a179`.
- Target is only OnePlus9R serial `b0644fb5`; no real mutation was performed in
  this review gate.

## Fresh read-only gate

- Installed package remains code `5`, name
  `0.1.0-business-acceptance.5`, APK SHA256
  `8b40b9284be9f6f7aca812792ff9315d9376803b9c6ec3d1ad9190241e0e5b0f`,
  signer SHA256
  `67a6d9af9e400326e1254b87ea310f34b1a1395664ca89424f141dbabba57796`.
- Process `21512` and exact user-0 accessibility binding were present; the
  sync service was absent/non-foreground, which is the exact recovery
  baseline required by the v6 harness.
- Cloud snapshot at `2026-09-28T17:34:23.356685+00:00` was
  `maintenance=false/version12`; binding/account/tenant identity was retained,
  both complete five-field occupancy maps were zero, receive-only notification
  mode remained enabled, and aggregate counts remained `379/23/14/6`.
- Shared lock was `FREE`; no target package staged session or local target
  installer process was observed. Unrelated vendor staged-session records were
  present and are not treated as target proof.

## State matrix

| Stage | Required state/request | Implementation |
| --- | --- | --- |
| Locked preflight | read `false/version12` | `install-oneplus-v6.py` validates exact 12 |
| Prepare current | read `false/version12` | `oneplus-v6-cloud.py` asserts exact 12 |
| Prepare CAS | `enabled=true`, `expectedVersion=12` | cloud helper sends exact 12 |
| Prepare acknowledgement | expected `true/version13` | local acknowledgement and ownership record require exact 13 |
| Maintenance observation | read `true/version13` | observation cloud gate requires exact 13 |
| Finish owned | `enabled=false`, `expectedVersion=13` | cloud helper sends exact 13 only after proven acknowledgement |
| Post observation | read `false/version14` | observation cloud gate requires exact 14 |
| Final verification | read `false/version14` | final gate requires exact 14 |
| Cleanup retry | `true/version13` to `false/version14`, or idempotent `false/version14` | identity-preserving owned helper only |

## Candidate and software evidence

- Private APK:
  `/Users/wangziheng/CloudCtlExternal/acceptance/20260929-v6/cloudctl-business-acceptance-v6.apk`.
- SHA256:
  `057ec5a303d447dbf7bdf74cd21d5e2c0d003a76a2de20987f516b4bc73dad0d`;
  package/version `com.company.cloudctl.companion`, `6`,
  `0.1.0-business-acceptance.6`; signer unchanged.
- Embedded source is clean `9c98c5f`; `DEBUG`, `HEARTBEAT_DIAGNOSTIC`, and
  `IM_UPLOAD_HOLD_ALLOWED` are false; recipe signing keys are `{}`.
- Full Android build: debug `1307/1307`, businessAcceptance `1293/1293`, no
  failures/errors/skips; assemble and all vital lint tasks succeeded.
- Focused Python harness plus lock tests: `99 passed`.

## Hold

The APK is built but not installed. No device lock was acquired, maintenance
was not changed, and no installer was invoked after the coordinator hold.
Real mutation requires review of this committed harness and a new explicit
execution delegation.
