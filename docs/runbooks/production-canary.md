# Production gates and five-percent canary

This runbook covers P5-007 software gates. It does not create production authorization and no
local, mock, synthetic, template or dry-run evidence can satisfy the hardware acceptance gate.

## Preconditions

- Obtain an approved, time-bounded release authorization for a named eligible device population.
- Bind the candidate release artifact SHA-256 and irreversible operations to a commit intent ID.
- Approve artifact, authorization, compatibility, observability, rollback and support gates.
- Select unique physical devices. `selectedCount / eligiblePopulation` must be at most 5 percent.
- Store canary, rollback, audit and review files with SHA-256 digests outside the repository.

## Canary contract

Each observation identifies a cohort device hash, unique sample/correlation IDs, authorized
timestamps, outcome, duration, commit status, audit completeness and evidence references.
Irreversible actions additionally require a unique action ID and the release commit intent ID.

Validation stops on insufficient samples or duration, more than 5 percent selection, threshold
regression, any safety violation, unknown commit, duplicate irreversible action, audit gap, missing
release gate, untested rollback or missing postmortem/release review.

## Offline validation

```bash
.venv/bin/python scripts/validate-rollout-evidence.py \
  --task-id P5-007 /secure/external-evidence/p5-007.json \
  --report /secure/external-evidence/p5-007-validation.json
```

## Release and rollback review

1. Recalculate cohort percentage from eligible and selected counts.
2. Verify all devices are physical, unique and match recorded Android/LAMDA/App versions.
3. Confirm thresholds, safety counters, commit states and audit completeness.
4. Run the approved rollback procedure and verify the declared stable version is restored.
5. Complete the postmortem/release review after canary and rollback, within authorization.
6. Archive source evidence and report; do not rewrite the source bundle as passed.
