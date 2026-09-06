# P2-005 evidence summary

- Task: 设备 Fencing Lease + LAMDA 60 秒锁
- Audited: 2026-08-31
- Software status: `implemented`
- Acceptance status: `blocked_hardware`

## Proven evidence

- Implementation/configuration: `packages/lamda-driver/src/cloudctl_lamda_driver/session.py`
- Implementation/configuration: `services/control-api/src/cloudctl_api/services.py`
- Software test evidence: `tests/edge_lamda_driver_test.py`
- Software test evidence: `tests/integration/test_backend_control_api.py`
- Local process evidence is explicitly classified `mock_only` with `hardwareEvidence=false`.

## Hardware boundary

No authorized Android/LAMDA device evidence, signed APK installation evidence, or production device result is present. Mock, simulator, and source-structure tests are not hardware acceptance.

