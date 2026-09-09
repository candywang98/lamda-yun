package com.company.cloudctl.companion

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.os.Bundle

class ClipboardRelayActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val text = intent.getStringExtra(EXTRA_TEXT).orEmpty()
        if (text.isNotEmpty()) {
            getSystemService(ClipboardManager::class.java)?.setPrimaryClip(
                ClipData.newPlainText("cloudctl-input", text),
            )
        }
        finish()
    }

    companion object {
        const val EXTRA_TEXT = "cloudctl.clipboard.text"
    }
}
