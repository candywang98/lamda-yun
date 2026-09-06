# Threat model

Reviewed on 2026-08-31. This model covers the Control API, Web clients, Edge, device runners,
LAMDA adapter, Companion App, automation packages, artifact/evidence storage, and operational
tooling. It does not claim an independent production penetration test.

## Assets and trust boundaries

Critical assets are tenant data, authorized account bindings, media and APK artifacts, signing
keys, Edge identities, LAMDA service certificates, publish intent, immutable audit evidence,
device availability, and recovery material.

The public browser boundary terminates at the Control API. Browsers never receive device PEM
material or connect to device port 65000. The cloud-to-Edge boundary is an outbound authenticated
stream. The Edge-to-device boundary is owned by `packages/lamda-driver`; commands must retain the
lease ID and monotonically increasing fencing token. PostgreSQL is business truth, Temporal is
workflow history, S3-compatible storage is artifact/evidence truth, and Edge SQLite is a replay
spool only.

LAMDA executes in a dedicated Python 3.12 child process. Its IPC uses standard streams, has no TCP
listener, accepts a fixed operation allowlist, and reports only redacted driver errors. Media and
APK requests cross this boundary as digest and size metadata; the sidecar reopens and rehashes the
content-addressed Edge cache object instead of accepting arbitrary per-operation file paths.

## STRIDE analysis

| Threat | Attack path | Required control | Automated evidence |
| --- | --- | --- | --- |
| Spoofing | Forged proxy claims or development headers | Application-owned OIDC verification; production bypass disabled | `test_control_api_auth.py` |
| Spoofing | Replayed debug launch/relay token | Short TTL, one-time exchange, creator/admin ownership, revoke | `test_backend_debug_sessions.py` |
| Tampering | Modified automation, APK, media, or evidence | Digest/signature checks, safe URI schemes, immutable audit | repository and integration tests |
| Tampering | Sidecar is asked to read an arbitrary local path | Content-addressed cache root, digest/size recheck, symlink and containment rejection | `edge_lamda_sidecar_test.py` |
| Tampering | Stale worker writes after lease loss | Single runner, lease ID, monotonic fencing token | Edge spool, publish, and Chaos tests |
| Repudiation | Actor denies an approval or result | Request/workflow/device correlation and durable audit | operation approval/audit tests |
| Information disclosure | Cross-tenant object ID probing | Tenant-scoped repositories; foreign IDs return not found | `test_penetration_authorization.py` |
| Information disclosure | PEM/token in logs, exports, or source archive | Redaction, restricted export, source scanning | security boundary and export tests |
| Denial of service | Oversized token/JWKS/export or growing spool | Size/time limits, bounded queues, alerts, fail-closed disk handling | auth/export/Chaos tests |
| Elevation of privilege | Viewer invokes admin/audit/result APIs | Central RBAC and service-only callbacks | authorization penetration tests |
| Elevation of privilege | Human spoofs executor result | `system_service` role and validated evidence URI | operation authorization tests |
| Irreversible duplication | Commit retried after uncertain result | `commit_intent -> commit_once -> reconcile`; one attempt | workflow and integration tests |

## Explicitly prohibited capabilities

Arbitrary shell, remote ADB/SSH, Frida, MITM, CAPTCHA handling, anti-detection, fake traffic,
account farming, and unauthorized bulk actions are absent from production capabilities. Browser
and cloud deployable configuration must not expose device port 65000.

## Local security acceptance

```bash
.venv/bin/python scripts/security-acceptance.py
```

The suite checks repository boundaries, authentication, RBAC, cross-tenant object access,
separation of duties, unsafe evidence references, debug-session ownership, and secret echo. Every
error response must retain an `X-Request-Id`/`correlation_id` without reflecting credentials.

## Residual and external risks

- Independent authenticated penetration testing against the production ingress and identity
  provider is still required.
- Certificate revocation, trust-root separation, and LAMDA/device behavior require an authorized
  lab or production-like environment.
- Cloud IAM, object-store policies, database row-level defenses, network policy, and WAF/rate-limit
  configuration require deployment-specific review.
- A local mock or template is never hardware or production acceptance evidence.
