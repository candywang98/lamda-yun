# P3-011 evidence summary

- Task: APK 验证、暂停与回滚
- Audited: 2026-08-31
- Software status: `implemented`
- Acceptance status: `blocked_hardware`

## Proven evidence

- Implementation/configuration: `packages/lamda-driver/src/cloudctl_lamda_driver/apk.py`
- Implementation/configuration: `apps/web/src/views/ApkRolloutView.vue`
- Software test evidence: `tests/edge_lamda_driver_test.py`
- Software test evidence: `apps/web/e2e/smoke.spec.ts`
- Local process evidence is explicitly classified `mock_only` with `hardwareEvidence=false`.

## Hardware boundary

No authorized Android/LAMDA device evidence, signed APK installation evidence, or production device result is present. Mock, simulator, and source-structure tests are not hardware acceptance.

