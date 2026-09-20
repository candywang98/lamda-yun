package com.company.cloudctl.companion.live

import android.content.Context
import android.content.Intent
import android.util.Log
import com.company.cloudctl.companion.automation.CloudCtlAccessibilityService
import com.company.cloudctl.companion.network.CloudConnection

/**
 * WIRE3 (Q14): owns the device-side live session lifecycle that the sync
 * heartbeat drives. [poll] is called once per heartbeat; REST discovery says
 * whether an operator opened (or closed) a session for this device:
 *
 *  - no session -> any active controller is torn down (server closed it, or it
 *    expired; the server pushes CLOSED over the WS as well — this is the
 *    belt-and-braces path);
 *  - same session id -> nothing to do (the controller keeps streaming);
 *  - a NEW session id -> adopt a fresh controller and raise the one-shot
 *    MediaProjection confirmation dialog ([ProjectionConsentActivity]).
 *
 * The remote gesture sink forwards to the accessibility service; the epoch
 * argument is enforced by the gate BEFORE the sink is called (see BLK-008
 * remainder: the sink-side remoteTap does not re-check the fencing token —
 * hardening seam, audited at the gate).
 */
object LiveSessionCoordinator {
    private const val TAG = "CloudCtlLive"

    @Volatile
    private var activeController: LiveSessionController? = null

    private val gestureSink = object : RemoteGestureSink {
        override fun remoteTap(epoch: Long, x: Double, y: Double) {
            val service = CloudCtlAccessibilityService.active
            if (service == null) {
                Log.w(TAG, "remote tap dropped: accessibility service not active")
                return
            }
            service.remoteTap(x, y)
        }

        override fun remoteSwipe(epoch: Long, x1: Double, y1: Double, x2: Double, y2: Double) {
            val service = CloudCtlAccessibilityService.active
            if (service == null) {
                Log.w(TAG, "remote swipe dropped: accessibility service not active")
                return
            }
            service.remoteSwipe(x1, y1, x2, y2)
        }
    }

    /** Call on the IO dispatcher; one REST GET per heartbeat. */
    fun poll(
        context: Context,
        connection: CloudConnection,
        unfinishedTaskRows: () -> Boolean = { false },
    ) {
        val current = activeController
        val candidate = LiveSessionController.checkForSession(
            context,
            connection,
            gestureSink,
            unfinishedTaskRows = unfinishedTaskRows,
        )
        when {
            candidate == null -> {
                // 404: no live session for this device anymore.
                current?.let { retire(it, "SESSION_GONE") }
            }
            candidate.sessionId == current?.sessionId -> {
                // Same session still streaming; discard the duplicate handle.
            }
            else -> {
                current?.let { retire(it, "SUPERSEDED") }
                activeController = candidate
                Log.i(TAG, "live session discovered sid=${candidate.sessionId}, requesting projection consent")
                ProjectionConsentActivity.start(context)
            }
        }
    }

    /** Forwards the MediaProjection dialog result to the owning controller. */
    fun onProjectionResult(granted: Boolean, resultCode: Int, data: Intent?) {
        val controller = activeController
        if (controller == null) {
            Log.w(TAG, "projection result without an active controller (granted=$granted)")
            return
        }
        controller.onProjectionResult(granted, resultCode, data)
    }

    private fun retire(controller: LiveSessionController, cause: String) {
        if (activeController === controller) activeController = null
        runCatching { controller.stop(cause) }
            .onFailure { Log.w(TAG, "live retire failed cause=$cause", it) }
    }
}
