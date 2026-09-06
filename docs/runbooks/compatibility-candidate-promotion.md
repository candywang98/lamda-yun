# Compatibility matrix and candidate promotion

This runbook covers P5-003 software preparation. It does not authorize device access and does
not turn a template, mock, synthetic run, dry-run or local result into hardware acceptance.

## Preconditions

- Obtain a time-bounded authorization ticket naming the approver and physical-device scope.
- Use an external authorized collector to produce immutable results and SHA-256 evidence files.
- Declare the required Android and LAMDA versions and the target App's N and N-1 versions.
- Record device serials only as SHA-256 hashes. Never include device PEM material or secrets.
- Keep the candidate package version and SHA-256 identical to `automationPackage` in the bundle.

## Matrix contract

Create one matrix cell for every declared Android x LAMDA x App release-level combination.
Each cell records the physical device model, architecture, root profile, LAMDA channel, App
package/signature, stable samples, candidate samples and a tested rollback. Stable and candidate
samples require unique sample and correlation IDs and evidence references whose file digests match.

The declared policy must require at least 72 hours of candidate soak. Candidate promotion is
rejected when a cell is missing, a track has too few samples, the failure or regression threshold
is exceeded, a safety violation or unknown commit appears, or rollback proof is absent.

## Offline validation

```bash
.venv/bin/python scripts/validate-rollout-evidence.py \
  --task-id P5-003 /secure/external-evidence/p5-003.json \
  --report /secure/external-evidence/p5-003-validation.json
```

The report is written separately and the source bundle is never rewritten. A passing validator
report is only valid for the external evidence it hashes. Repository status remains
`blocked_hardware` until authorized evidence is actually supplied and reviewed.

## Promotion review

1. Verify every declared coverage cell appears exactly once.
2. Confirm N and N-1 identify distinct App versions.
3. Review stable/candidate sample counts, failure rates, soak duration and safety counters.
4. Execute the authorized rollback procedure and attach its artifact/procedure evidence.
5. Record the reviewer and `PROMOTE` decision after all runs and rollback complete.
6. Archive the source bundle, referenced evidence files and separate validation report.
