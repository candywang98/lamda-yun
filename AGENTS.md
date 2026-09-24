# CloudCtl engineering rules

This repository implements the architecture in `docs/reference/`. Keep the following invariants in every change:

1. Only `packages/lamda-driver` may import `lamda`.
2. Browser and cloud services never connect to device port 65000 and never receive device PEM material.
3. Edge connections are outbound and authenticated; all device commands carry a lease ID and monotonically increasing fencing token.
4. A device has one active runner. Publish commit follows `commit_intent -> commit_once -> reconcile`; `commit_once` has one attempt.
5. PostgreSQL is the business source of truth, Temporal is execution history, S3 stores binaries/evidence, and Edge SQLite is a spool only.
6. Real-device tasks remain `blocked_hardware` until authorized hardware evidence exists. Mock tests never satisfy hardware acceptance.
7. Do not add arbitrary shell, ADB/SSH exposure, Frida, MITM, CAPTCHA handling, anti-detection, account farming, fake traffic, or unauthorized bulk actions.

## V1 execution ownership (ADR 0004)

**Production automation**:
- **Companion mobile-local** (`mobile/companion`): enrolled Android APK executes device tasks via accessibility without USB/ADB/Edge. Platforms: 闲鱼, 小红书, 抖音.
- **API publisher** (`services/control-api` publishers): server-side official API calls. Platforms: 微信公众号.

**Development/diagnostic only**:
- **Edge + LAMDA** (`edge/gateway`, `packages/lamda-driver`): Studio live layout inspection and evidence preview. Not required for production task delivery. Must not hold a write lease when Companion is enrolled.

V1 platform scope is exactly four: 闲鱼商品, 小红书图文, 抖音视频, 微信公众号文章. Other platforms are frozen for V1.

Keep edits inside your assigned component paths when parallel agents are active.

## Multi-agent development execution

This section governs development agents only. It does not turn the production
Temporal worker into an LLM agent runner.

### Controller and capacity

- One root Worker is the controller. It owns task selection, shared contracts,
  resource locks, integration, final verification, evidence indexing, and plan
  updates.
- When the runtime exposes sub-agent delegation and two or more READY work
  items have disjoint write scopes, the controller must launch the independent
  sub-agents in one batch and wait only after all launches. Do not launch one
  child and immediately await it before launching the next.
- Default capacity is one controller plus at most three writing sub-agents.
  Additional agents may perform read-only review, but do not increase writing
  concurrency without isolated worktrees and independent test resources.
- If the runtime has no real delegation capability, report
  `SUBAGENT_CAPABILITY_UNAVAILABLE`; do not simulate parallel completion.

### READY rule

A work item is READY only when all of the following are true:

1. Its required contracts or fixtures are frozen and available.
2. Its write scope does not overlap any running work item.
3. All required resource locks are free.
4. No unresolved shared-contract decision can change its implementation.
5. Its acceptance commands and evidence directory are declared.

An integration dependency does not require the other package to be completely
accepted before independent component development begins. It only gates the
cross-component acceptance run.

### Isolation and ownership

- Every writing sub-agent uses its own Git branch and worktree created from the
  same frozen baseline SHA. A shared dirty directory is not a safe parallel
  workspace.
- Before creating worktrees, the controller must create a reviewed, recoverable
  baseline checkpoint. Do not use `git add -A`; exclude caches, build output,
  APKs, SQLite/WAL files, runtime dumps, secrets, and unrelated evidence.
- Each work item declares `owned_paths` and `read_only_paths`. A sub-agent must
  stop and request a contract/ownership handoff before writing outside its
  owned paths.
- Sub-agents do not edit the authoritative Excel plan, shared generated OpenAPI
  clients, or final evidence index. The controller owns those files.
- Shared generated contracts are regenerated once by the controller after the
  implementation branches are integrated.

### Exclusive locks

The following locks are single-owner and therefore intentionally serialized:

- `CONTRACT:<name>` for a shared schema or state-machine decision.
- `DB_MIGRATION` for migration numbering, upgrade, and rollback.
- `MERGE:integration` for integration-branch changes.
- `DEVICE:<serial>` for APK install, claim, pause/resume, activation, or other
  writes to one physical device. The local tool is
  `scripts/device_lock.py` (see `docs/runbooks/device-acceptance-locks.md`).
  It stores one shared SQLite file in the Git common directory and is not
  production PostgreSQL `device_lease`. A missing database is only bootstrap
  state: FREE does not prove the phone is idle. The tool locks an exact
  serial only; pool or alias exclusion is an external stop, not something
  the lock can prove. Sub-agents do not acquire it.
- `DEPLOY:<environment>` for service deployment or restart.
- `RELEASE:<package>` for manual publish, revoke, or rollback.
- `SIDE_EFFECT:G3` for real publish, charge, delete, review, or promotion.

Only the controller/authorized acceptance operator may hold device, deploy,
release, or side-effect locks. Sub-agents prepare code and software tests but do
not independently operate production services or the shared OnePlus device.

### Child delivery contract

Every child result must include:

- work-item ID, baseline SHA, branch SHA, and owned-path diff;
- frozen contract/fixture version used;
- exact test commands, exit codes, and test counts;
- evidence directory and concise findings;
- unresolved gaps, required locks, and merge-order constraints.

The controller rejects results that cross path ownership, modify generated
caches, weaken security gates, lack executable evidence, or claim hardware
acceptance from mocks.

### Integration order

Development may run concurrently. Integration is a controlled queue:

1. Freeze or merge the shared contract/data model.
2. Merge Control API and its single migration, if any.
3. Rebase and merge Android and Web implementations against that contract.
4. Regenerate shared OpenAPI/TypeScript clients once.
5. Run cross-component tests on the same integration SHA.
6. With explicit authorization, run one serialized device/deployment acceptance
   queue and record task IDs, versions, hashes, and stop conditions.

Conflicts go back to the owning sub-agent. The controller must not resolve a
semantic contract conflict with mechanical `ours`/`theirs` choices.

The current executable template and P14 work-item queue are documented in
`docs/phase1/multi-agent-execution.md` and
`docs/phase1/multi-agent-work-items.json` (HISTORICAL since 2026-09-16).

## Single active task source (fleet-first-20260916.1)

Since R02 activation (2026-09-16), the authoritative machine task source is
`docs/current/tasks.json`. Read `docs/current/README.md` first. Task states use
`dev_state` (NOT_STARTED/IN_PROGRESS/SOFTWARE_DONE) and `acceptance_state`
(NOT_RUN/SOFTWARE_ACCEPTED/DEVICE_WAIT/DEVICE_ACCEPTED/BLOCKED) as separate
fields. Validate changes with `python scripts/plan_guard.py
docs/current/tasks.json`. Legacy Excel plans under `docs/project-plans/` are
read-only baselines until their migration is verified; progress text never
overrides safety gates.

