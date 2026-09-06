# Local runtime acceptance

`scripts/local-acceptance.py` verifies the Control API and Edge Companion HTTP contracts across
real loopback process boundaries. It uses only temporary memory/SQLite state and a mock Edge
supervisor. The command never starts a LAMDA session or contacts a device.

Run the complete suite from the repository root:

```bash
.venv/bin/python scripts/local-acceptance.py \
  --component all \
  --report artifacts/runtime/local-acceptance.json
```

The independently restartable components are useful while diagnosing startup failures:

```bash
.venv/bin/python scripts/local-acceptance.py --component control
.venv/bin/python scripts/local-acceptance.py --component edge
```

The suite exits nonzero on the first failed contract. A successful JSON report always contains
`"evidenceClass": "mock_only"` and `"hardwareEvidence": false`.

## Covered contracts

- Control API live/ready health and required OpenAPI paths.
- The 15-module catalog and all 134 stable feature IDs, including exact per-module counts.
- Operation task create, list, get, cancel, audit, pending approval, separation of duties, and
  approval release.
- Debug session create, one-time launch-code exchange, get, heartbeat, evidence registration, and
  revoke. Launch-code replay and post-revoke heartbeat are also denied.
- Edge Gateway network-free `--check` startup.
- Companion one-time enrollment, device-bound bearer authorization, health upload, snapshot,
  confirmation, and emergency stop.

## Evidence boundary

Passing this suite proves local composition, routing, persistence behavior, and HTTP contracts. It
does not prove any Android APK was built or installed, and it is not evidence of a real device,
real LAMDA connectivity, certificate provisioning, media delivery, or automation execution. Those
items remain `blocked_hardware` until evidence is captured from explicitly authorized hardware.
