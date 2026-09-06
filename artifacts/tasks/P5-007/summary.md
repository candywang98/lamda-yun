# P5-007 evidence summary

- Task: production gates, five-percent canary and release review
- Audited: 2026-08-31
- Software status: `implemented`
- Acceptance status: `blocked_hardware`
- Hardware evidence: `false`

## Software preparation delivered

The offline rollout validator checks required release gates, candidate artifact and commit intent,
explicit eligible/selected cohort counts, a maximum five-percent physical-device cohort, unique
device/sample/correlation IDs, minimum samples and observation duration, failure and
stable-regression thresholds, zero safety violations/unknown commits/duplicate irreversible
actions/audit gaps, evidence SHA-256, tested stable-version rollback and completed postmortem.

The existing Automation Registry staged policy remains unchanged. The new tool validates only
externally supplied results and never rewrites source evidence as passed.

## Hardware blocker

No approved production-like device population, real five-percent canary, rollback drill or release
review bundle was supplied. `hardwareEvidence` remains false and acceptance is blocked.
