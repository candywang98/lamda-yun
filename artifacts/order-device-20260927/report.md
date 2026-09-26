# OnePlus Business Restore, 2026-09-27 +08:00

Follow-up: [unplugged attempt and v3 fix](unplugged-report.md). The user has
since disconnected USB; cloud claim worked but v2 rejected the new sidecar at
admission. The tested v3 correction is available for authenticated manual
download, not yet installed or device-accepted.

## Result

User confirmed that the phones were idle and approved updating the collectors.
Only OnePlus serial `b0644fb5` was present in `adb devices -l`; no Huawei phone
or wireless alias was attached. OnePlus was updated in place at
`2026-09-27T00:14:25+08:00` through `00:14:31+08:00`.

Cloud received the new build heartbeat at `00:14:32.384255+08:00`:
`companionVersion=0.1.0-business-acceptance`, `accessibilityEnabled=true`,
`runnerState=IDLE`, `orderDeliveryProtocol=order-delivery/1`.
This proves installation and capability advertisement, not real collection or
continuous background connectivity. No new collection task was dispatched.
USB remained connected. O10 remains **IN_PROGRESS / DEVICE_WAIT**.

## Artifact And Trust

- Source base `b1f07f1`, with the focused `businessAcceptance` build variant
  and its three variant-specific tests added in this change.
- Package `com.company.cloudctl.companion`, versionCode **2**,
  versionName `0.1.0-business-acceptance`.
- APK SHA256 `b882b9a7368498ea63072b1c92806c170aaf80b688a24dcce4ee37195232a086`.
- APK signing certificate SHA256
  `67a6d9af9e400326e1254b87ea310f34b1a1395664ca89424f141dbabba57796`,
  exactly matching the APK pulled from the phone before installation.
- Main plus release sources; non-debuggable; no diagnostic gate or IM hold
  switch; no extra permission or debug/acceptance receiver.
- Old and new APK BuildConfig fields were inspected directly. The existing
  test update public key and empty recipe-key set are unchanged.
- This is an explicit **phase-one business acceptance build, not a production
  release**. Existing debug signing and test update trust still require separate
  production hardening. The release controlled-key guard was not weakened.
- Version 1 is not a normal forward rollback from version 2. A recovery build
  requires an appropriately newer version and data compatibility; do not
  uninstall, erase data, or force a downgrade.

## Preservation And Safety

Before installation, two consecutive complete app database copies, including
available WAL/journal sidecars, were byte-stable; SQLite `quick_check=ok`.
The private backup also includes app preferences, files and the original APK.
The binding and database bytes were checked again immediately before install.

- Local task states: 30 `TERMINAL_CONFIRMED`, 1 `TERMINAL_REJECTED`.
- Pending event uploads: zero. Existing 247 event and 277 journal rows retained
  in the verified pre-install backup.
- No independent IM outbox database or durable order delivery tables existed
  in the old install; there was no persisted IM upload hold to resume.
- No active cloud lease, nonterminal task, schedule, preview, debug session, or
  pending APK release target at preflight.
- Exact-serial local device lock fencing **9**, acquired `00:13:25+08:00`,
  released `00:15:14+08:00`.
- OnePlus maintenance false/version4 -> true/version5 using normal operator
  authentication and expectedVersion. Restored false/version6 and read back.
- `adb install -r` succeeded once. No uninstall, clear-data, force-stop,
  permission change, rebind, phone navigation, or Huawei operation.
- Pulled installed APK hash matches the verified artifact. Original first
  install timestamp, 11 parsed permission grants and four secure settings
  (accessibility, notification listeners, enabled/default IME) are unchanged.
- Cloud active binding ID and token digest match the pre-install record.
- The new package is non-debuggable: post-install private SQLite contents were
  **not** re-read. Binding continuity is verified at the cloud, not represented
  as a byte-for-byte post-install database comparison.
- Cloud tasks remained 376, outgoing messages 23; receiveOnly=true and
  NOTIFICATION mode unchanged. No sending, publishing, delisting or trade.

## Verification

From `mobile/companion`:

```sh
./build-external.sh --offline :app:testBusinessAcceptanceUnitTest :app:assembleBusinessAcceptance :app:lintBusinessAcceptance --console=plain
./build-external.sh --offline :app:testBusinessAcceptanceUnitTest --console=plain
./build-external.sh --offline :app:verifyReleaseUpdatePublicKey --console=plain
```

The first two commands exited 0. JUnit: **173 suites / 1265 tests**, zero
failures/errors/skips. Lint: 19 warnings, no Error/Fatal. Existing SDK/deprecation
warnings remain. The third command deliberately tested the release guard:
exit 1, rejecting the missing controlled update key as expected.

Independent read-only Android review found no blocking build-variant defect.
Concrete APK checks covered versionCode2, original package, complete certificate,
unchanged requested permissions/update keys, business flags and sync service.
The APK analyzer wrapper failed on a pre-existing SDK path-with-spaces issue;
direct invocation of its Java CLI completed the same read-only inspection.

Sanitized evidence: `artifact-summary.json`, `install-summary.json`,
`cloud-post.json`. Raw app data, screenshots, credentials and lock token remain
outside Git in the protected private scratch directory.

## Next Gates

1. User physically disconnects OnePlus USB and disables wireless ADB, retaining
   network access. Cloud-only read-only order collection and receipt/Web checks
   follow; no Edge or ADB navigation may supply the business execution.
2. The two Huawei devices still need installation/permission verification.
   P30 Pro remains network-connected on the old build; P30's pre-existing
   maintenance=true/version1 was not changed.
3. Browser space18 remains handed to the user. Visual acceptance has not run.
4. Historical account isolation, legacy/durable mixed-channel projection
   behavior and production update trust remain separate gaps.
5. Long-term background stability stays separate; this work does not reopen
   the B11 endurance investigation or make it a single-device prerequisite.
