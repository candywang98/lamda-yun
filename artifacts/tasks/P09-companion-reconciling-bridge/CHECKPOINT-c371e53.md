# P09-package checkpoint RUN c371e53ddf634786b540da04aa7b49e6

## Status — HALTED

Controller stop-and-handoff. Do not continue this RUN_ID.

- M1 KEEP + tested 13/0/0: AutomationStore.kt `b581f49ec69dd956ab555dab234a9e8ecab5d2e742b44af9e4a6ac6bb5a8ae92`, Test `2603dd30397e80ffab4b83a1c1b7a7de9c94dd1fd3e762e0a7f453f0efb4f1d9`
- M2 KEEP + tested 8/0/0: IrreversibleActionGate.kt `def81d9f309843989c77133474c4f2a68f71200f6ef3c222c2ff064c1329159f`, Test `386d6ae79a51353f49164876b9d5bb0603ccd7b7b9d610cd8e47cc14f8ac1adb`
- M3 WRITTEN UNTESTED: Coordinator.kt `db76d8db9e15c7a0786fc900f1483cdfaa626e54564dbc6ccc1248a4fbe31efd`, Test `d2fff8fc7648f474902caa73f556c1a8578096084f2726e0ba9122ca4677705c` (18:49:45)
- M4 NOT STARTED: platform_tasks.py / test_platform_tasks.py read-only, mtime 2026-09-08

Bound result: `artifacts/tasks/P08-command-v1-resume/result-P09-package-c371e53ddf634786b540da04aa7b49e6.md`
VERDICT: STOPPED_BY_RULE

## Wiring constraints (still valid for next RUN)

- recordActionIntent: null->INTENT; APPLIED->APPLIED; INTENT/UNKNOWN->UNKNOWN
- Gate: fresh INTENT invokes once; APPLIED skip; INTENT/UNKNOWN -> RECONCILE_REQUIRED no invoke
- enqueueStepEventLocked: RECONCILING event requires task STATE_RUNNING (do NOT markPaused)
- persistResumeRejected is pause path — do not use for UNKNOWN
- Ban: real recipes, P08 rewrite, P14, device, deploy, sign, G3 claims

## Next (new RUN only)

1. Verify outbox JSON shape vs CoordinatorTest nested `payload` asserts
2. Run CoordinatorTest + KEEP Store/Gate tests; copy XML
3. M4 pytest + mobile_service RECONCILING ingest if missing
4. New result file for the new RUN_ID
