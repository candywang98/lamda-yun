# CloudCtl development report

Date: 2026-08-31

## Delivered system

The architecture package is implemented as 16 logical projects: 9 deployable applications/services,
6 shared contract or domain packages, and 1 infrastructure/operations project.

Deployable applications and services:

1. Vue Web management console.
2. Vue/Monaco Automation Studio.
3. FastAPI Control API.
4. Temporal publish worker.
5. Edge Hub gRPC service library.
6. Transactional Outbox dispatcher.
7. Edge Gateway runtime.
8. Android Companion APK project.
9. Optional Android Enterprise DPC APK project.

Shared packages:

1. Domain model and RBAC.
2. Edge protobuf/gRPC protocol.
3. Isolated LAMDA driver.
4. Automation SDK and manifest validation.
5. Observability helpers.
6. OpenAPI and TypeScript API client contracts.

Infrastructure includes Compose dependencies, Caddy, OpenTelemetry, Prometheus, Grafana, Terraform,
backup/restore, certificate rotation, Edge install/upgrade, CI, security checks, ADRs, runbooks, threat
model, and compatibility documentation.

## Competitor feature parity layer

The Web console now includes the complete competitor information architecture as a governed operations
catalog: 15 business modules, 134 menu entries, and 111 unique source routes. Every entry is reachable from
the sidebar and catalog and has its own PDF page reference, source title and route, summary, domain fields,
and four-step workflow. Search, filters, row selection, batch confirmation, role-aware actions, saved views,
JSON/CSV export, record details, task receipts, and desktop/mobile navigation are implemented.

Unsafe or unsupported capabilities remain visible for product mapping but are policy-blocked. Actions that
can change external state require a scoped target preview and approval semantics. The generic Control API
adds a strict 15-module allowlist, tenant/RBAC filtering, idempotent single and batch task creation, target
results, cooperative cancellation, audit aggregation, and transactional outbox events. It cannot bypass
the dedicated publish, approval, device-maintenance, or APK safety workflows.

The server-side 134-entry inventory is explicit about completion state: 16 entries have approved operation
mappings, 22 are policy `blocked`, and 96 are `ui_only` with no approved backend operation. The default local
deployment exposes two real built-in validators, `works.revision.validate` and
`publish_plans.snapshot.validate`. Other approved mappings remain `contract_only` unless their explicit
HTTP/Bearer executor adapter is configured. Unavailable executors reject new tasks instead of returning a
misleading queued receipt.

The Outbox dispatcher now consumes `operation.task.created` and `operation.task.approved` idempotently. It
supports the two built-in validators and fixed-contract HTTP adapters, preserves retryable events when an
executor is unavailable, checks cancellation before dispatch, records RUNNING/terminal item state, rejects
late results after cancellation, and writes service-actor audit events. This proves the execution framework;
it does not claim that undeployed external adapters or device-side operations have run.

The control plane now also implements tenant-scoped platform-account authorization and device binding,
checksum-bound S3 media uploads, media asset and derivative tracking, and immutable content revisions with
archive and group membership APIs. Secret-store references are never returned by the API, production keeps
the PostgreSQL and S3 requirements, and an explicitly configured production S3 endpoint must use HTTPS.

Automation package admission verifies an Ed25519 statement binding the artifact, normalized manifest, SBOM
reference, and SBOM digest. Rollout promotion is constrained to 0%, 5%, 25%, and 100% and derives production
qualification only after the final evidence gate. APK admission records signed analysis reports, SBOMs,
permission/SDK/ABI findings, and policy decisions instead of accepting caller-asserted scan status.

The Edge and Companion contracts now carry typed task state, current step, cancelability, device health,
APK/media artifact metadata and delivery progress, confirmation risk, operator actions, and emergency-stop
state while retaining the legacy `currentTask` fallback.

Production authentication verifies OIDC JWTs inside the application with RS256/ES256, issuer, audience,
time, key-use, and key-rotation checks; ASGI scope claims are not trusted. Development authentication now
requires explicit tenant, user, role, and MFA headers instead of silently assuming an administrator.
Production requires PostgreSQL/asyncpg and S3 and never auto-creates schema. Alembic revisions `0001` through
`0005` cover the control-plane baseline, Operations/Debug Session persistence, Debug Session fencing,
accounts/media/content groups, and signed supply-chain attestations, including migration contract checks.

The Studio examples use the real Python Automation SDK. Its lifecycle enforces
`validate -> preflight -> prepare -> before_commit -> commit_once -> reconcile -> cleanup`, and controlled
tap, text input, and swipe operate only through signed locator registries and declared capabilities.

## Verification result

- Ruff formatting and lint: passed.
- Pyright: 0 errors, 0 warnings.
- Mypy strict: 0 issues across 90 source files.
- Python unit, integration, replay, security, operations, migration, authentication, archive, and contract tests: 259 passed.
- Web unit tests: 23 passed; Web Playwright E2E: 20 passed and 8 desktop-only catalog batches skipped on mobile. The desktop run traversed all 134 competitor-aligned pages; shared flows and invalid-route handling passed on desktop and 390 x 844 mobile profiles.
- Studio unit tests: 9 passed; Studio Playwright E2E: 2 passed.
- TypeScript contract package: lint, typecheck, test, and build passed.
- Web and Studio production builds: passed.
- Android debug builds: on 2026-08-31, Companion and DPC both completed `assembleDebug` with Gradle 8.10.2, Android Gradle Plugin 8.7.3, compile/target SDK 35, and minimum SDK 29. The Companion build required and received a source fix removing an invalid internal `weight` import from `MainActivity.kt`.
- Companion APK: 54,377,889 bytes; SHA-256 `2346514784cce4f301b9e3f9613815efcfdca194da33b964347beb0d31873ff2`; package `com.company.cloudctl.companion`; version `0.1.0` (`versionCode=1`); APK Signature Scheme v2 Debug signature verification passed.
- DPC APK: 54,213,810 bytes; SHA-256 `90fb68621094a4f9a218b49fcf50d643f3d3a8ef5f02cb684128ecaefd806634`; package `com.company.cloudctl.dpc`; version `0.1.0` (`versionCode=1`); APK Signature Scheme v2 Debug signature verification passed.
- Android device smoke: both APKs installed successfully on device `b0644fb5`, an LE2100 / OnePlus9R running Android 14. Companion cold-started in approximately 1,201 ms, notification permission was granted, and its registration screen rendered normally. DPC cold-started in 881 ms and its policy screen rendered normally. Crash and ANR scans were clean.
- DPC ownership remained intentionally unconfigured: `dpm list-owners` returned `no owners`, and no provisioning was performed. Evidence is stored under `outputs/android-device/oneplus9r-20260831/android-build-install`.
- Screenshot note: third-party package `com.ydydyd8818` continuously displayed an overlay across the top of the device screenshots. This overlay is external to CloudCtl and is not attributed to either CloudCtl APK.
- Repository security boundary script: passed.
- Operational acceptance covers local ASGI load, Edge offline replay/restart, fencing loss, SQLite full-disk integrity, and synthetic PostgreSQL/Temporal/object-store recovery. These are local evidence and do not replace production capacity or disaster-recovery drills.
- SLO recording/alert rules, Alertmanager routing, a Grafana dashboard, audit export, runbooks, and authorization boundary tests are included; production monitoring, paging, and independent penetration testing remain pending.
- Local process acceptance: 9 Control API, Operations, Debug Session, Edge, and Companion groups passed; the two locally deployed Operations validators are asserted explicitly; report classified `mock_only` with `hardwareEvidence=false`.
- Live browser acceptance: Web loaded all 15 modules/134 entries, displayed PDF page 51 and the original route for `product-management-09`, created/listed/audited a `works.revision.validate` task, and Studio loaded the Python SDK/Monaco workspace with no fresh browser warnings or errors; evidence remains `mock_only`.
- Live configuration acceptance: an authorized role created and reloaded tenant-scoped feature drafts, stale writes returned `409`, Viewer writes returned `403`, validation limits returned `422`, and the browser restored the saved `assets-01` values at version 2. `blocked` and `ui_only` entries retained draft-save controls but remained non-executable; evidence remains `mock_only` because the local API used its in-memory repository and development identity headers.
- Authorized P2-011 diagnostics: a read-only run completed on an LE2100 / OnePlus9R with Android 14 / SDK 34. Inventory, command audit, screenshot, UI hierarchy, run result, and checksums were captured with `mutatingOperationsExecuted=false`. LAMDA was unavailable, so this is physical-device diagnostic evidence rather than LAMDA acceptance; the task remains `blocked_hardware` with `hardwareEvidence=false`.
- P5-003, P5-006, and P5-007 software preparation is implemented: offline contracts and validators cover the compatibility matrix/candidate promotion, paired AutoJS/CloudCtl comparison, production gates, five-percent canary, rollback, and release review. No authorized external matrix, dual-track, or production-canary bundle was supplied, so their acceptance remains `blocked_hardware`.
- Task-level evidence ledger: 58 of 59 architecture tasks have explicit software implementation evidence. Software implementation does not imply hardware acceptance, and no task is marked acceptance-done from mock, template, dry-run, or local-only evidence.
- Evidence checksums: 58 task manifests and 219 referenced entries passed SHA-256 verification.

The Android results establish successful Debug APK compilation, v2 Debug-signature verification, installation,
and basic launch/UI smoke on one physical device. They do not constitute release-signing verification, DPC
provisioning/ownership validation, complete `connectedCheck`, real LAMDA acceptance, APK upgrade/rollback,
compatibility promotion, AutoJS dual-run, long-run/chaos, or production-rollout acceptance. Task-ledger
acceptance states are unchanged, and the remaining hardware-required work stays `blocked_hardware` until its
task-specific authorized evidence is supplied.

## Safety invariants

- Only `packages/lamda-driver` imports the third-party LAMDA SDK.
- Browsers and cloud services never access device port 65000 or device PEM material.
- A newer fencing token invalidates stale work and each device has a single active Runner.
- Irreversible submission follows `commit_intent -> commit_once -> reconcile`; commit is never auto-retried.
- Production capabilities exclude arbitrary shell, Frida, MITM, CAPTCHA bypass, anti-detection, fake traffic,
  and unauthorized bulk actions.

See `task-status.md` and `task-status.json` for all 59 architecture tasks. No task is marked acceptance-done
without its own evidence; hardware-required tasks are not misreported as complete based on mock evidence.
