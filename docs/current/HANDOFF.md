# Saved checkpoint: explicit resumption only

The user stopped for sleep. Do not continue autonomously until the user explicitly
resumes. This checkpoint is NOT new device, installation or business authorization.
Executor preference: GPT-6 Astra / Low; parent plans/reviews. Files cannot select
the model; disclose unavailability instead of silently substituting an executor.

## Start here, without repeating the review

- Verified SOFTWARE baseline: `f52cec1e133e22b4529778c95527c33a188aab3d`.
- `0433e814f056091c8efadcf0973633a30f24f327` is already an ancestor/merged.
- The code baseline was normally pushed. Parent checked clean main at
  `2026-09-29T17:46:13Z`; this is historical, not a fresh startup check.
- This handoff is a LOCAL-ONLY docs commit, not pushed tonight. Its own SHA is
  intentionally not embedded. After parent integration, docs-only ahead-of-origin
  is expected; determine actual branch/HEAD/status locally.
- Accept commits above the verified baseline only when their entire diff is
  limited to `AGENTS.md` and `docs/current/HANDOFF.md`. Any other drift requires a
  targeted check of changed/affected code, not a full re-audit or automatic tests.
- Reuse unchanged evidence. Do not inspect all sibling worktrees/history or chats.

## State and preserved evidence

- `docs/current/tasks.json` remains the sole task-state authority.
- Ledger SHA256: `3a1ae74049ba843bc66a77d4a0cb98be259130897ff324b17d106e5d6bb46fcb`.
- All 54 IDs / 108 dev_state + acceptance_state fields remain unchanged.
- Main's 42 old untracked files are preserved, not cleanup targets.
- f52 adds only two real coroutine-cancellation regression tests: 11 class tests
  included within 93 IME package tests, all passed. This does NOT prove a phone's
  keyboard is fixed, restored or hardware-accepted.
- Evidence root: `/Users/wangziheng/CloudCtlExternal/acceptance/20260930-ime-cancel-regression/`.
- Test evidence: `attempt-UYZQ8I/SUMMARY.md` under that root.
- Integration evidence: `integration-1dX1P5/SUMMARY.md` under that root.

## Last known CI observation, not current status

- Observed `2026-09-29T17:24:05Z` / `2026-09-30 01:24:05 Asia/Shanghai`.
- Run `36604004938`, SHA `f52cec1e133e22b4529778c95527c33a188aab3d`.
- Frontend `109528260515`: success.
- Python `109528260611`: in_progress; no final counts available at that observation.
- Android `109528260282`: failure at `Require Android release update public key`.
- Source: `wrapup-observation-9xc9AC/observation.json` under the evidence root above.
- State may have changed. After explicit resumption, query THIS existing run once;
  never restart it or reuse an earlier SHA's Python test counts.

## Remaining scope and authorization

- Acceptance scope: at least 2 phones with real incoming messages; product flow
  only through pre-publication on 1 phone; screen sharing plus end/handoff on 1 phone.
- No third-phone or cable-unplug requirement. ADB is optional authorized diagnostics,
  never a production business-runtime prerequisite.
- Planned candidates: 9R `b0644fb5`, VOG `APH0219624006517`.
- ELE `GBGDU19830002425` is excluded. Do not expand to all connected phones.
- Missing: controlled `CLOUDCTL_APP_UPDATE_PUBLIC_KEY` from the release owner.
- Missing: explicit VOG idle installation/recovery window; NOT received.
- Keyboard recovery and 2+1+1 hardware evidence remain absent.
- VOG candidate is prepared, NOT installed:
  `/Users/wangziheng/CloudCtlExternal/acceptance/20260929-vog-v7/cloudctl-vog-recovery-v7.apk`.
- APK SHA256: `57f5f444566fdd3878db036eadb70f130d067092a231a4320f8bade39b6bfcb0`.
- Before any specifically authorized installation, freshly verify device
  identity/signature/version, cloud identity/account/occupancy, staged sessions
  and the exclusive device lock. Cached readiness is not current permission.
- No tenant migration, account rebind, real sending/publishing, settings changes,
  deployment or installation without specific authorization. No other-chat access.

## Next action after explicit resume

Lightweight Git/status/diff check, then one read of the existing CI run. If external
authorization or release-owner key input remains missing, report the exact missing
input and stop that path. Do not turn waiting into another test/code-audit loop.
Do not schedule continuation or create a goal/automation from this checkpoint.
