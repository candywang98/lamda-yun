package com.company.cloudctl.testtarget;

import android.app.Activity;
import android.app.Dialog;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;

import java.util.UUID;

/**
 * Q12 controlled-fault fixture surface (故障台账与恢复测试夹具).
 *
 * Beyond the original deterministic button/confirm page, the activity now
 * simulates the four fault-fixture primitives the Q12 task card mandates:
 *
 * <ul>
 *   <li><b>unique target</b> — {@code arm_button} mints a per-run
 *       {@code TARGET_TOKEN <uuid>} shown on {@code target_card}; the gated
 *       confirm dialog embeds the same token, so a strike is always provable
 *       against ONE unique target instead of a positional cardIndex=0 into a
 *       real shop list.</li>
 *   <li><b>delay</b> — after arming, {@code action_button} stays disabled for
 *       {@link #ARM_DELAY_MS} (late-arriving target: exercises polling
 *       budgets and no-progress exits of the executor under test).</li>
 *   <li><b>confirmation</b> — {@code action_button} opens
 *       {@code dialog_confirm} ({@code confirm_button} / {@code cancel_button});
 *       the strike executes exactly once per confirm and is counted.</li>
 *   <li><b>boot/session markers + execution ledger</b> —
 *       {@code boot_marker} shows {@code BOOT#n PAGE#m} (process restart vs
 *       page reopen, persisted via {@link FixtureLedger#PROCESS_BOOTS} /
 *       {@link FixtureLedger#PAGE_OPENS}) and {@code execution_ledger} shows
 *       the persisted execution counters; both are externally readable from
 *       the accessibility tree, independent of the system under test.</li>
 *   <li><b>input focus preemption</b> — {@code focus_thief_button} steals
 *       focus from {@code input_field} mid-input and bumps the persisted
 *       {@code FOCUS_LOSS} counter (the InputProof fail-closed fault).</li>
 * </ul>
 *
 * The app remains side-effect-free: no network, no shell, no ADB, no dynamic
 * code, no privileged capability — only local UI state and SharedPreferences.
 */
public final class MainActivity extends Activity {

    /** How long the gated action button stays disabled after arming. */
    static final long ARM_DELAY_MS = 1500L;

    private String runToken = "";
    private TextView statusText;
    private TextView bootMarker;
    private TextView executionLedger;
    private TextView targetCard;
    private TextView resultPanel;
    private EditText inputField;
    private Button actionButton;
    private final Handler handler = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        // Page-reopen marker: every activity creation bumps PAGE# while
        // BOOT# only moves on a real process restart (see TestTargetApp).
        FixtureLedger.bump(getApplicationContext(), FixtureLedger.PAGE_OPENS);

        statusText = findViewById(R.id.status_text);
        bootMarker = findViewById(R.id.boot_marker);
        executionLedger = findViewById(R.id.execution_ledger);
        inputField = findViewById(R.id.input_field);
        targetCard = findViewById(R.id.target_card);
        actionButton = findViewById(R.id.action_button);
        resultPanel = findViewById(R.id.result_panel);
        Button armButton = findViewById(R.id.arm_button);
        Button focusThiefButton = findViewById(R.id.focus_thief_button);

        renderMarkers();
        actionButton.setOnClickListener(view -> onActionTapped());
        armButton.setOnClickListener(view -> onArmTapped());
        focusThiefButton.setOnClickListener(view -> onFocusStolen());
    }

    private void onArmTapped() {
        // Unique target for this run: a fresh token, never a list position.
        runToken = "q12-target-" + UUID.randomUUID().toString();
        int armed = FixtureLedger.bump(getApplicationContext(), FixtureLedger.RUNS_ARMED);
        targetCard.setText(getString(R.string.target_pending, runToken));
        targetCard.setVisibility(View.VISIBLE);
        resultPanel.setVisibility(View.GONE);
        actionButton.setEnabled(false);
        handler.postDelayed(() -> {
            // Delayed readiness: the target becomes actionable only now.
            targetCard.setText(getString(R.string.target_armed, runToken, armed));
            actionButton.setEnabled(true);
            renderMarkers();
        }, ARM_DELAY_MS);
        renderMarkers();
    }

    private void onActionTapped() {
        FixtureLedger.bump(getApplicationContext(), FixtureLedger.ACTION_TAPS);
        renderMarkers();
        if (runToken.isEmpty()) {
            resultPanel.setText(R.string.result_not_armed);
            resultPanel.setVisibility(View.VISIBLE);
            return;
        }
        showConfirmDialog();
    }

    private void showConfirmDialog() {
        final Dialog dialog = new Dialog(this);
        dialog.setContentView(R.layout.dialog_confirm);
        TextView token = dialog.findViewById(R.id.confirm_dialog_token);
        TextView ledger = dialog.findViewById(R.id.confirm_dialog_ledger);
        Button confirm = dialog.findViewById(R.id.confirm_button);
        Button cancel = dialog.findViewById(R.id.cancel_button);
        token.setText(getString(R.string.confirm_dialog_token, runToken));
        ledger.setText(ledgerLine());
        confirm.setOnClickListener(view -> {
            int strikes =
                    FixtureLedger.bump(getApplicationContext(), FixtureLedger.CONFIRM_STRIKES);
            resultPanel.setText(getString(R.string.result_struck, runToken, strikes));
            resultPanel.setVisibility(View.VISIBLE);
            dialog.dismiss();
            renderMarkers();
        });
        cancel.setOnClickListener(view -> {
            int cancels =
                    FixtureLedger.bump(getApplicationContext(), FixtureLedger.CONFIRM_CANCELS);
            resultPanel.setText(getString(R.string.result_cancelled, runToken, cancels));
            resultPanel.setVisibility(View.VISIBLE);
            dialog.dismiss();
            renderMarkers();
        });
        dialog.show();
    }

    private void onFocusStolen() {
        // Deterministic input-focus preemption fault: steal focus from the
        // structured input and record it in the persistent ledger.
        if (inputField.hasFocus()) {
            FixtureLedger.bump(getApplicationContext(), FixtureLedger.FOCUS_LOSSES);
        }
        findViewById(R.id.focus_thief_button).requestFocus();
        renderMarkers();
    }

    private String ledgerLine() {
        return getString(
                R.string.ledger_line,
                FixtureLedger.read(getApplicationContext(), FixtureLedger.ACTION_TAPS),
                FixtureLedger.read(getApplicationContext(), FixtureLedger.CONFIRM_STRIKES),
                FixtureLedger.read(getApplicationContext(), FixtureLedger.CONFIRM_CANCELS),
                FixtureLedger.read(getApplicationContext(), FixtureLedger.FOCUS_LOSSES));
    }

    private void renderMarkers() {
        bootMarker.setText(
                getString(
                        R.string.boot_marker,
                        FixtureLedger.read(getApplicationContext(), FixtureLedger.PROCESS_BOOTS),
                        FixtureLedger.read(getApplicationContext(), FixtureLedger.PAGE_OPENS),
                        FixtureLedger.read(getApplicationContext(), FixtureLedger.RUNS_ARMED)));
        executionLedger.setText(ledgerLine());
        statusText.setText(
                runToken.isEmpty() ? R.string.status_ready : R.string.status_armed);
    }
}
