# CloudCtl Companion

`com.company.cloudctl.companion` is the user-visible companion application. Enrollment talks only to
the certificate-pinned Control API HTTPS endpoint, never to a PC-side browser, ADB bridge, relay, or
the LAMDA service port. The binding token is encrypted with an Android Keystore key; LAMDA PEM
material is not stored by the app.

Build with JDK 17 and Android SDK 35:

```bash
./gradlew lint testDebugUnitTest assembleDebug
```

The debug build uses a public RFC 8032 update-signature vector only for deterministic unit tests. A
release build rejects that key and requires the controlled X.509 Ed25519 public key through either
`CLOUDCTL_APP_UPDATE_PUBLIC_KEY` or `-Pcloudctl.appUpdatePublicKey=...`.

The release signing key is intentionally absent. Production signing belongs in controlled CI/HSM
configuration.

## Direct mobile execution P0

The Companion contains a direct-cloud execution runtime that does not use a PC, ADB, Edge browser,
gateway relay, shell commands, or downloaded code. `CompanionSyncService` claims leases from
`/companion/v2`, durably stores tasks and ordered outbox events in app-private SQLite, and delegates
only the seven structured actions in `mobile-automation-task.schema.json` to a non-exported
`AccessibilityService`.

Keep-alive is the foreground service plus accessibility, not a 24-hour screen lock. After binding,
Companion asks the operator to ignore battery optimizations and reports that flag on the 20s device
heartbeat. Boot, unlock, package replace, and Android 14 foreground-service timeout schedule a restart
only when a cloud binding already exists.

The production execution chain is:

```text
Web workbench -> Control API -> Companion foreground service -> local queue
              -> Accessibility executor -> durable outbox -> Control API
```

Edge, ADB and screen mirroring are development diagnostics only. They must not be running for the
no-USB production acceptance test.

The build targets the independently deployed Companion executor package
`com.company.cloudctl.companion`. Android applies a strict locator rule: `locatorRef` resolves only
to an exact reviewed resource ID or content description for the self-developed executor UI.
Coordinates, shell, ADB, scripts, reflection and dynamic code are intentionally unsupported.

Interrupted `RUNNING` tasks are marked `FAILED_RESTART` and are never blindly replayed. Every step
has its own timeout in addition to the task deadline. Input values are never copied to journals or
outbox events. The signed task payload itself is currently stored in the application-private,
non-backed-up SQLite database, so sensitive input remains recoverable on a rooted/compromised
device; production task authors should prefer short-lived secret references rather than embedding
long-lived credentials.
