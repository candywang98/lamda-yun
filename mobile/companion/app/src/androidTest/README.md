# P14 device storage instrumentation delivery

Work item: `p14-device-storage-tests`. Branch: `agent/p14-device-storage-tests`.
Baseline: `80a5de9dd7635bb2cff70ea13fb262cbb0e7d11d`.
Frozen contract: `contracts/phase1/p14-recipe-version-contract.md`, recipe-version/20260909.1.
Owned scope and delivery evidence: `mobile/companion/app/src/androidTest/` only.

Three AndroidJUnit4 tests use real RecipePackageManager, RecipeLifecycle and AutomationStore:

- An exact IOException during the absent new identity's download preserves the old package and catalog across reopening.
- Truncated signed JSON throws JSONException during install and preserves the old package and catalog across reopening.
- A stale package.json.tmp cannot replace the complete old package on restore or reinstall.

Each case checks persisted active/pending snapshots, the active version, old bytes and canonical hash, signature-verified loading, exact-command lookup without downloading, and absence of a new package. Reopening closes SQLite, clears the in-memory recipe catalog and creates fresh storage/lifecycle instances.

Isolation uses only InstrumentationRegistry.getInstrumentation().context (test APK). A ContextWrapper routes SQLite into a unique directory under that context's cacheDir, alongside isolated package files. Cleanup removes only that directory after closing the store; no deleteDatabase calls or targetContext access.

Fixture `assets/recipes/published-probe.json` is a byte-for-byte copy of the baseline's `src/test/resources/recipes/published-probe.json` (signed manifest version 1.0.1, phase1-recipe-1 public key from RecipeLifecycleTest). The truncated asset is its prefix, ending inside the signature digest string. Old/new references intentionally share the valid body's hash but use distinct server version IDs. No private keys are included.

Validation performed: `git diff --check`, exit 0. Instrumentation tests authored: 3; tests executed: 0. No build, ADB, device operation, deployment, or runtime evidence collected. Compilation and Android execution remain unverified; hardware acceptance remains blocked_hardware.

Parent-only verification, from mobile/companion:

```sh
./gradlew :app:assembleDebugAndroidTest
./gradlew :app:connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=com.company.cloudctl.companion.updates.RecipeStorageInstrumentationTest
```

The execution command requires the parent's authorized DEVICE lock. Parent owns build/run results and final evidence indexing; this directory contains implementation evidence only. Integration requires MERGE:integration; no schema or production source dependency beyond the baseline APIs.
