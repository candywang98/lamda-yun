package com.company.cloudctl.testtarget;

import android.app.Activity;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;

public final class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        EditText input = findViewById(R.id.input_field);
        TextView result = findViewById(R.id.result_panel);
        Button action = findViewById(R.id.action_button);
        action.setOnClickListener(view -> {
            String value = input.getText().toString().trim();
            result.setText(value.isEmpty() ? R.string.result_empty : R.string.result_complete);
            result.setVisibility(View.VISIBLE);
        });
    }
}
