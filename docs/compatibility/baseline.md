# Compatibility baseline

Baseline date: 2026-08-30

| Component | Candidate | Stable/rollback | Evidence required |
| --- | --- | --- | --- |
| LAMDA | 10.8 | 10.6 | 72-hour authorized-device soak, lock, locator, remote, APK, publish reconciliation |
| Android | 10-17 | Per device profile | Device model, OS build, ABI, root profile, permissions |
| Target application | Current supported N | N-1 when explicitly supported | Package/version/signature, locator bundle, authorized account |
| Automation package | Signed candidate | Previous signed stable | Manifest, SBOM, signature, contract tests |

Mock Device and Mock Edge evidence validates software paths only. It does not promote a hardware compatibility row.

