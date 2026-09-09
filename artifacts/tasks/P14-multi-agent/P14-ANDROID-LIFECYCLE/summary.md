# P14-ANDROID-LIFECYCLE delivery

Baseline: `364c264e21dfcc0464a8537b95f2445af9f35fcf`
Branch: `agent/p14-android-lifecycle`
Contract: `recipe-version/20260909.1`

Implemented RecipeReference validation, immutable signed package persistence via fsync + atomic directory publication, exact version/hash/engine checks and safe paths; RecipeLifecycle catalog restoration/staging/activation, historical exact-version claim download and rollback; durable active/pending catalog in AutomationStore schema v4; task payload comparison retains recipe pin across lease updates; active execution and pause/reconciliation block version activation. CompanionSyncService calls these paths at startup, synchronization and command execution.

## Root verification

Worker timed out with build produced and test process still finishing. Root collected XML: a new Robolectric test suite selected SDK 28 despite minSdk 29; explicitly set SDK 35. One malformed-input test altered JSON using string replacement that did not match escaped slashes; Root changed it to mutate JSON fields directly, retaining failure assertions.

With JAVA_HOME/SDK/Gradle resources from `/Users/wangziheng/CloudCtlExternal` and separate project cache `project-cache/p14-android`, command:

```
./gradlew --no-daemon --max-workers=2 --project-cache-dir <external>/project-cache/p14-android testDebugUnitTest --tests '*RecipeLifecycleTest' --tests '*RecipeCatalogTest' --tests '*RecipeEngineTest' --tests '*RecipeSignatureVerifierTest' --tests '*AutomationStoreTest' assembleDebug
```

Result: **BUILD SUCCESSFUL in 1m 15s**, **47 tests, 0 failures, 0 errors, 0 skipped** independently counted from 5 JUnit XML reports (22 lifecycle tests). Log `/tmp/lamda-p14-android-verification.log`.

APK: `mobile/companion/app/build/outputs/apk/debug/app-debug.apk`
SHA-256: `52fba6a4e335225ac7329f05f6c349cc50819077a59908ce966466becc28a2d7`.

These are software/module results. Root owns signing/install, browser/backend integration and real-device acceptance; none is claimed by this module report.
