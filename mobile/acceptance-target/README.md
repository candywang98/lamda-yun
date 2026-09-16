# CloudCtl acceptance target

This deterministic app exists only for authorized no-USB acceptance of the
Companion's structured Accessibility executor. Its package is the Companion's
default allowlisted package: `com.company.cloudctl.testtarget`.

It contains no network, shell, ADB, dynamic code, or privileged capability.

## Q12 fault-fixture extension (version 0.2.0)

The app now simulates the fault-fixture primitives the Q12 task card
mandates, replacing the old real-shop `cardIndex=0` targeting of the Q02-B
device scenarios:

- **Unique target** — `arm_button` mints a per-run `TARGET_TOKEN <uuid>` on
  `target_card`; the confirmation dialog embeds the same token, so every
  gated strike is provable against ONE unique target, never a positional
  card in a real shop list.
- **Delay** — after arming, `action_button` stays disabled for ~1.5 s
  (`TARGET_PENDING` → `TARGET_TOKEN … ARMED`), exercising late-arriving
  targets / polling budgets / no-progress exits of the executor under test.
- **Confirmation** — `action_button` opens `dialog_confirm`
  (`confirm_button` = CONFIRM_STRIKE, `cancel_button` = CANCEL_STRIKE); the
  strike executes exactly once per confirmation.
- **Boot/session markers** — `boot_marker` renders
  `BOOT#<process_boots> PAGE#<page_opens> RUNS#<runs_armed>` from persisted
  counters. `BOOT#` increments only on a real process restart (Application
  onCreate); a page reopen increments only `PAGE#`. A restart-recovery
  verification without a `BOOT#` increment is a page reopen and must not
  count as restart recovery (the Q02-B1 hollow-pass lesson).
- **Execution ledger** — `execution_ledger` renders
  `TAPS=<n> STRIKES=<n> CANCELS=<n> FOCUS_LOSS=<n>` (persisted via
  SharedPreferences). These are the externally observable ACTUAL execution
  counts, readable from the accessibility tree independently of the cloud
  system under test.
- **Input focus preemption** — `focus_thief_button` steals focus from
  `input_field` and bumps the persisted `FOCUS_LOSS` counter (the
  ui-observation/v1 §4 InputProof fail-closed fault injector).

## Approved locator refs

Legacy refs (`status_text`, `input_field`, `action_button`, `result_panel`)
keep their meaning; `action_button` now opens the confirmation dialog instead
of completing directly. Q12 additions: `root_panel`, `boot_marker`,
`execution_ledger`, `focus_thief_button`, `arm_button`, `target_card`, and in
`dialog_confirm`: `confirm_dialog_root`, `confirm_dialog_title`,
`confirm_dialog_token`, `confirm_dialog_ledger`, `confirm_button`,
`cancel_button`.

Note: the Companion's `TargetLocatorRegistry` does not yet allowlist this
package for automated steps; on-device execution of the unique-target strike
requires a controller decision to register the fixture locators (tracked as
Q12 device-pending item `q12-device-unique-target-confirm-strike`).
