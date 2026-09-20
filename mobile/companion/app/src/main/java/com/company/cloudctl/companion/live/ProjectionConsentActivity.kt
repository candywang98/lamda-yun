package com.company.cloudctl.companion.live

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import android.util.Log

/**
 * WIRE3 (Q14): the one-shot MediaProjection user-confirmation host. The
 * system dialog this activity launches is the ONLY consent path for screen
 * capture (K13 §6: every session needs its own live confirmation; the grant
 * is single-use and session-bound in [ProjectionGrantRegistry]).
 *
 * Launched from the sync service context — fleet devices grant the
 * SYSTEM_ALERT_WINDOW appop so a background activity start is permitted.
 */
class ProjectionConsentActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState != null) {
            // Recreation after process death: the coordinator already holds
            // the session; a fresh dialog would be a second confirmation.
            finish()
            return
        }
        val manager = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        runCatching {
            startActivityForResult(manager.createScreenCaptureIntent(), REQUEST_CODE)
        }.onFailure {
            Log.w("CloudCtlLive", "projection consent launch failed", it)
            LiveSessionCoordinator.onProjectionResult(false, RESULT_CANCELED, null)
            finish()
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQUEST_CODE) {
            finish()
            return
        }
        LiveSessionCoordinator.onProjectionResult(resultCode == RESULT_OK, resultCode, data)
        finish()
    }

    companion object {
        private const val REQUEST_CODE = 7001

        fun start(context: Context) {
            val intent = Intent(context, ProjectionConsentActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
        }
    }
}
