package com.company.cloudctl.testtarget;

import android.content.Context;
import android.content.SharedPreferences;

/**
 * Persistent, externally observable execution counters for the Q12 fault
 * fixture (故障台账).
 *
 * Every counter is persisted in SharedPreferences AND mirrored into the
 * accessibility tree by {@link MainActivity}, so an external verifier (the
 * Companion under test, an operator, or a test harness) can read the ACTUAL
 * number of executions from the UI tree without trusting the cloud system
 * under test — the Q12 requirement "每个场景输出实际执行次数和外部独立可观测状态".
 *
 * The counters intentionally survive process restarts and page reopens:
 *
 * <ul>
 *   <li>{@code process_boots} increments once per OS process (Application
 *       onCreate). A real process restart / reboot bumps it; merely
 *       reopening the page never does — the anti-hollow-pass marker for the
 *       old Q02-B1 restart scenario.</li>
 *   <li>{@code page_opens} increments on every activity creation, so
 *       {@code BOOT#n PAGE#m} with n unchanged and m incremented proves a
 *       page reopen, while both incrementing proves a process restart.</li>
 * </ul>
 */
public final class FixtureLedger {

    public static final String PREFS = "cloudctl.testtarget.fixture";

    public static final String PROCESS_BOOTS = "process_boots";
    public static final String PAGE_OPENS = "page_opens";
    public static final String RUNS_ARMED = "runs_armed";
    public static final String ACTION_TAPS = "action_taps";
    public static final String CONFIRM_STRIKES = "confirm_strikes";
    public static final String CONFIRM_CANCELS = "confirm_cancels";
    public static final String FOCUS_LOSSES = "focus_losses";

    private FixtureLedger() {
    }

    public static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public static int read(Context context, String key) {
        return prefs(context).getInt(key, 0);
    }

    /** Increment {@code key} and return the new value. */
    public static int bump(Context context, String key) {
        int next = read(context, key) + 1;
        prefs(context).edit().putInt(key, next).apply();
        return next;
    }
}
