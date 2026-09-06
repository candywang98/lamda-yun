# P2-006 evidence summary

- Task: 设备发现、能力探测与心跳
- Audited: 2026-08-31
- Software status: `implemented`
- Acceptance status: `blocked_hardware`

## Proven evidence

- Implementation/configuration: `edge/gateway/src/cloudctl_edge/device_registry.py`
- Implementation/configuration: `edge/gateway/src/cloudctl_edge/runtime.py`
- Software test evidence: `tests/edge_runtime_test.py`
- Software test evidence: `tests/edge_gateway_test.py`
- Local process evidence is explicitly classified `mock_only` with `hardwareEvidence=false`.

## Hardware boundary

No authorized Android/LAMDA device evidence, signed APK installation evidence, or production device result is present. Mock, simulator, and source-structure tests are not hardware acceptance.

