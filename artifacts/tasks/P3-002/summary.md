# P3-002 evidence summary

- Task: 自动化包 Registry、签名与灰度
- Audited: 2026-08-31
- Software status: `implemented`
- Acceptance status: `pending`

## Implemented closure

- Registry admission verifies an Ed25519 signature from a configured trusted key.
- The signed statement binds the artifact SHA-256, normalized manifest, SBOM reference, and SBOM SHA-256.
- Packages enter at 0% and can advance only through 5%, 25%, and 100%.
- Promotion requires minimum samples, zero safety violations, and a bounded failure rate.
- `production_qualified` is derived only after the 100% promotion gate; callers cannot self-assert it.
- Registration and promotion are persisted, audited, and emitted through outbox events.
- Migration `20260831_0005` resets legacy self-qualified packages to 0% and unqualified.
- OpenAPI and the TypeScript client expose the signed registration and promotion contracts.

## Verification

- Supply-chain/API/migration/contract suite: 31 passed.
- Full Python suite: 159 passed.
- Ruff, Pyright, and Mypy passed.
- TypeScript contract typecheck/build passed.

## Remaining external gates

Production acceptance remains pending until production signing public keys are configured and real rollout telemetry proves each promotion stage. No production key material is included in the repository.
