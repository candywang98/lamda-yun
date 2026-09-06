# AutoJS dual-track comparison

This runbook covers P5-006 evidence comparison only. The CloudCtl validator does not execute,
modify or package AutoJS and must not be used to gain device or account access.

## Preconditions

- Obtain a time-bounded authorization ticket for the physical devices, target App and scenarios.
- Collect AutoJS baseline and CloudCtl candidate results outside this validator.
- Hash each scenario input before execution and preserve result files with SHA-256 digests.
- Record physical-device Android/LAMDA/App/package/signature versions for every paired sample.

## Pairing contract

Every `pairId` contains an `AUTOJS` baseline and `CLOUDCTL` candidate with identical
`scenarioId` and `inputSha256`. Each track records a unique sample ID, correlation ID, timestamps,
outcome, duration, safety violations, immutable artifact digest and evidence references.

The comparison is rejected when the pair count is below policy, identities differ, the candidate
failure/outcome-regression/p95-duration thresholds are exceeded, evidence is incomplete, a safety
violation or unknown commit exists, or tested rollback proof is missing.

## Offline validation

```bash
.venv/bin/python scripts/validate-rollout-evidence.py \
  --task-id P5-006 /secure/external-evidence/p5-006.json \
  --report /secure/external-evidence/p5-006-validation.json
```

## Migration review

1. Verify the authorization window contains every baseline, candidate and rollback timestamp.
2. Confirm each pair uses the same scenario and input digest.
3. Review failure rate, outcome regressions and p95 duration ratio from the validator report.
4. Confirm all referenced evidence hashes and the candidate package hash.
5. Review the tested rollback and record the `MIGRATE` decision only after paired runs finish.
6. Keep repository acceptance `blocked_hardware` when no authorized external bundle exists.
