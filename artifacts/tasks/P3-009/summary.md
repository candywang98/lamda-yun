# P3-009 evidence summary

- Task: APK 入库、静态分析、SBOM 与策略
- Audited: 2026-08-31
- Software status: `implemented`
- Acceptance status: `pending`

## Implemented closure

- APK admission requires an Ed25519-signed analyzer report from a configured trusted key.
- The report is bound to APK SHA-256, package/version, signer digest, SDK levels, ABIs, permissions, and SBOM SHA-256.
- Policy rejects stale or future reports, non-CLEAN verdicts, debuggable APKs, cleartext traffic, unsupported ABIs, low target SDKs, denied permissions, and HIGH/CRITICAL findings.
- Source and SBOM references must use credential-free HTTPS, OCI, or S3 references.
- The API derives `scan_status=CLEAN`; callers cannot self-assert a scan result.
- The registry persists the analysis report, analyzer key, signature digest, and policy decision, then writes audit and outbox evidence.
- Migration `20260831_0005` downgrades legacy self-reported CLEAN artifacts to PENDING reanalysis.
- OpenAPI and TypeScript contracts include the analyzer report and signature fields.

## Verification

- Supply-chain/API/migration/contract suite: 31 passed.
- Full Python suite: 159 passed.
- Ruff, Pyright, and Mypy passed.
- TypeScript contract typecheck/build passed.

## Remaining external gates

Production acceptance remains pending until an authorized analyzer service, trusted production analysis key, object storage, and real APK/SBOM inputs are configured. No APK was installed and no device evidence is claimed.
