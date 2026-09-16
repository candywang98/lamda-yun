package com.company.cloudctl.testtarget;

import android.app.Application;

/**
 * Process-restart marker for the Q12 fault fixture.
 *
 * onCreate runs exactly once per OS process, so incrementing
 * {@link FixtureLedger#PROCESS_BOOTS} here is the reliable, externally
 * observable signal that separates a REAL process restart (force-stop,
 * crash, reboot) from merely reopening the activity — the distinction the
 * old Q02-B1 restart scenario lacked, which let it pass vacuously.
 */
public final class TestTargetApp extends Application {

    @Override
    public void onCreate() {
        super.onCreate();
        FixtureLedger.bump(getApplicationContext(), FixtureLedger.PROCESS_BOOTS);
    }
}
