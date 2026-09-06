# P3-012 evidence summary

- Task: 授权测试账号真机发布验收
- Audited: 2026-08-31
- Software status: `unverified`
- Acceptance status: `blocked_hardware`

## Software gate delivered

The task-specific evidence validator and offline preparation runner require an authorized physical device, account authorization evidence, publish prepare/commit/reconcile checks, a durable commit intent, correlation/workflow identifiers, and checksum-bound files. The checked-in authorization and run-result templates are explicitly dry-run inputs: they do not write an acceptance bundle or set `hardwareEvidence=true`.

The preparation runner only assembles a final bundle from `AUTHORIZED_EXTERNAL_RUNNER` and `PHYSICAL_DEVICE` input, requires matching SHA-256 device serial hashes, and routes the written result through the final validator. Mock, emulator, dry-run, pending, secret-bearing, or incomplete bundles are rejected.

The validator proves the acceptance boundary, not a completed real-account publish run. The full task remains `unverified` until its executor and authorized-device workflow produce evidence.

## Hardware blocker

No authorized test account plus physical LAMDA device was supplied. Acceptance remains `blocked_hardware` and `hardwareEvidence` remains false.
