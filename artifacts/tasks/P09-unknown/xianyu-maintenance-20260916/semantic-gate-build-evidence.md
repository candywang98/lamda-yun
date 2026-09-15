# P09 semantic delete gate build evidence

- Recorded at: 2026-09-16 02:41:22 CST (Asia/Shanghai)
- Branch / source: integration/p14-20260909 @ 48005da-dirty
- APK: mobile/companion/app/build/outputs/apk/debug/app-debug.apk
- APK SHA-256: c6353cdd3d70625a962dc5c21abff989530d2ee89701df1bce914c03b87c15f7
- Embedded SOURCE_REVISION: 48005da-dirty
- Android final full unit suite: 380 tests, 0 failures, 0 errors, 0 skipped
- Backend full suite: 662 passed, 1 skipped
- Final focused regression after review: production gate selection + published card locator, 16 tests, 0 failures
- Production wiring: delete-v2 semantic locator xianyu_delete_confirm now constructs XianyuMaintenanceCommitGate; ordinary taps do not; legacy layout confirms remain supported.
- Card safety: title is anchor only; full remaining-list wrappers, full-scroll wrappers, degenerate and unsafe rectangles fail closed.
- Exactly-once adapter: one authorization, one tapOnce, UNKNOWN persistence, second invocation reconcile-only.
- Device side effect status: no confirmation gesture and no deletion performed at this checkpoint.
