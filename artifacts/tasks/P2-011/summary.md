# P2-011 evidence summary

- Task: 真机只读 Smoke 与支持矩阵
- Audited: 2026-08-31
- Software status: `implemented`
- Acceptance status: `blocked_hardware`

## Software gate delivered

The repository now includes an allowlisted ADB diagnostic runner, a task-specific physical-device evidence validator, automated negative/positive fixtures, offline evidence preparation, and P2-011 contract templates. The runner exposes inventory, package inspection, screenshot capture, and UI hierarchy dump only. It records operation names without raw command arguments or device serials.

Focused runner and evidence tests passed (`43 passed`). The latest repository-wide Python regression passed (`259 passed`). Ruff, Mypy, and Pyright also passed for the changed software and tests.

## Authorized diagnostic run

The authorized physical-device diagnostic completed on 2026-08-31 at `07:33:22Z` and produced an integrity-bound evidence directory at `device-evidence/oneplus9r-20260831/`.

| Device | Android | Target package | Read-only result | LAMDA result |
| --- | --- | --- | --- | --- |
| LE2100 / OnePlus9R | 14 / SDK 34 | `com.android.settings` 14.0.0 | PASS | UNAVAILABLE |

The target package was inspected without launching it. Because input actions were prohibited, the screenshot and UI dump capture the device's existing foreground state. The command audit confirms `mutatingOperationsExecuted=false`.

## Hardware blocker

This is real physical-device diagnostic evidence, but it is not acceptance-grade LAMDA evidence. No LAMDA package was detected, port 65000 was not listening, the LAMDA SDK version was unavailable, and the support matrix contains only one diagnostic row. The acceptance validator additionally requires `execution.transport=LAMDA_DRIVER` and a usable LAMDA version. Therefore `hardwareEvidence=false` and `acceptanceStatus=blocked_hardware` remain mandatory.
