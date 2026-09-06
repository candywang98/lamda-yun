# ADR 0003: Mobile-local production execution

- Status: accepted
- Date: 2026-09-01

## Decision

Production automation is executed by the enrolled Android Companion on the phone. The control
workbench persists and dispatches a signed, structured task directly to the APK over HTTPS. The APK
persists the task before acknowledgement, executes only its compiled allowlist of accessibility
actions, journals every transition locally, and reliably uploads redacted events and evidence.

The production path is:

`Web workbench -> Control API -> Companion APK -> Android AccessibilityService -> Control API`

Edge, ADB, scrcpy, and USB are development and diagnostic tools only. They are not required for task
delivery, task execution, cancellation, evidence capture, or result reporting.

## Required properties

- The phone continues after the workstation, ADB server, USB cable, and local Edge are unavailable.
- A task is a bounded schema, never arbitrary code, shell, coordinates, intents, file paths, or ADB.
- The APK accepts only its enrolled device ID, target package, unexpired task, and known action types.
- `taskId + canonical digest` is idempotent; reuse with different content fails closed.
- One device has at most one active task. Task and step state survive process death and reboot.
- Mutation actions are not blindly retried. A lost response is resolved with a postcondition or marked
  unknown for operator review.
- Screenshots remain in app-private storage until uploaded, are content-addressed, and are deleted
  after the durable upload acknowledgement.
- Accessibility permission is explicitly granted by the device user or authorized administrator. The
  DPC cannot silently grant it and is not the automation executor.

## Acceptance test

1. Enroll the APK to an HTTPS Control API endpoint and enable its visible accessibility and foreground
   synchronization services.
2. Stop the workstation Edge process and ADB server, then make USB unavailable.
3. Submit a structured task from the workbench.
4. Verify the phone independently receives, persists, executes, and uploads ordered step events,
   screenshot evidence, and a terminal result.
5. Restart the APK process during a non-mutating step and verify recovery from the local journal.

