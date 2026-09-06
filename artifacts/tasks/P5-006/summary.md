# P5-006 evidence summary

- Task: AutoJS dual-track migration pilot
- Audited: 2026-08-31
- Software status: `implemented`
- Acceptance status: `blocked_hardware`
- Hardware evidence: `false`

## Software preparation delivered

The offline rollout validator consumes paired external AutoJS baseline and CloudCtl candidate
results with identical authorized scenario/input identities. It verifies physical-device versions,
unique samples/correlations, authorization timestamps, evidence SHA-256, candidate package digest,
minimum pairs, failure and outcome-regression thresholds, p95 duration regression, zero safety
violations/unknown commits, tested rollback and a reviewed migration decision.

The validator does not execute, modify or package AutoJS. Mock, synthetic, template, dry-run and
local-only data cannot satisfy the external hardware evidence class.

## Hardware blocker

No authorized paired AutoJS/CloudCtl physical-device results were supplied. The repository makes
no migration acceptance claim and `hardwareEvidence` remains false.
