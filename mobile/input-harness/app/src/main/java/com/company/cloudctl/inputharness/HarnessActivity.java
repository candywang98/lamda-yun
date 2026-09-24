package com.company.cloudctl.inputharness;

import android.app.Activity;
import android.os.Bundle;
import android.widget.EditText;

/**
 * Shows one empty multiline field and nothing else.
 * No click listeners, no clipboard, no network, no business navigation.
 */
public final class HarnessActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_harness);
        EditText field = findViewById(R.id.harness_multiline_field);
        field.setText("");
    }
}
