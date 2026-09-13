package com.company.cloudctl.companion.live

import android.content.Context
import android.content.Intent
import android.util.Log
import com.company.cloudctl.companion.network.CloudConnection
import com.company.cloudctl.companion.network.PinnedHttpsTransport
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/**
 * Companion side of a live session (p10-live/20260913.1): polls REST status,
 * streams frames over the companion WS, and executes remote inputs through the
 * accessibility gesture channel. Never uses shell input.
 */
class LiveSessionController(
    private val context: Context,
    private val connection: CloudConnection,
    private val gestures: RemoteGestureSink,
) {
    private val machine = LiveClientStateMachine()
    private val client = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .sslSocketFactory(
            PinnedHttpsTransport.pinnedSocketFactory(connection.certificateSha256),
            com.company.cloudctl.companion.network.PinnedTrustManager(connection.certificateSha256),
        )
        .build()
    private var socket: AtomicReference<WebSocket?> = AtomicReference(null)
    private var activeSid: String? = null

    fun onProjectionResult(granted: Boolean, resultCode: Int, data: Intent?) {
        val sid = activeSid ?: return
        Thread { ack(sid, granted, resultCode, data) }.start()
    }

    private fun ack(sid: String, granted: Boolean, resultCode: Int, data: Intent?) {
        runCatching {
            val body = JSONObject().put("granted", granted)
            val (status, _) = PinnedHttpsTransport.request(
                connection.baseUrl, "/companion/v2/live/$sid/ack",
                connection.certificateSha256, "POST",
                mapOf(
                    "Authorization" to "Bearer ${connection.bearerToken}",
                    "Content-Type" to "application/json",
                ),
                body.toString().toByteArray(Charsets.UTF_8), 10_000, 15_000,
            )
            Log.i(TAG, "live ack sid=$sid granted=$granted status=$status")
            if (granted && data != null && status == 200) {
                startCapture(resultCode, data)
                connectSocket(sid)
            }
        }.onFailure { Log.w(TAG, "live ack failed", it) }
    }

    private fun startCapture(resultCode: Int, data: Intent) {
        val intent = Intent(context, MediaProjectionService::class.java)
            .putExtra(MediaProjectionService.EXTRA_RESULT_CODE, resultCode)
            .putExtra(MediaProjectionService.EXTRA_RESULT_DATA, data)
        context.startForegroundService(intent)
    }

    fun sendFrame(jpegBase64: String) {
        socket.get()?.send(JSONObject().put("t", "frame").put("jpeg", jpegBase64).toString())
    }

    fun setRemote(remote: Boolean) {
        if (remote) machine.onTakeControl() else machine.onRelease()
    }

    private fun connectSocket(sid: String) {
        val request = Request.Builder()
            .url("${connection.baseUrl.replace("https://", "wss://")}/companion/v2/live/$sid")
            .header("Authorization", "Bearer ${connection.bearerToken}")
            .build()
        socket.set(client.newWebSocket(request, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                val message = runCatching { JSONObject(text) }.getOrNull() ?: return
                when (message.optString("t")) {
                    "state" -> {
                        when (message.optString("state")) {
                            "REMOTE" -> setRemote(true)
                            "VIEWING" -> setRemote(false)
                            "CLOSED" -> {
                                machine.onClosed()
                                stop()
                            }
                        }
                    }
                    "input" -> handleInput(message)
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: okhttp3.Response?) {
                Log.w(TAG, "live socket failure", t)
                machine.onClosed()
            }
        }))
    }

    private fun handleInput(message: JSONObject) {
        if (machine.state != LiveClientState.REMOTE) return
        val seq = message.optInt("seq", 0)
        if (!machine.guard.accept(seq)) {
            Log.w(TAG, "dropping stale remote input seq=$seq")
            return
        }
        when (message.optString("kind")) {
            "tap" -> gestures.remoteTap(message.optDouble("x"), message.optDouble("y"))
            "swipe" -> gestures.remoteSwipe(
                message.optDouble("x"), message.optDouble("y"),
                message.optDouble("x2"), message.optDouble("y2"),
            )
            else -> Log.w(TAG, "unsupported remote input kind=${message.optString("kind")}")
        }
    }

    fun stop() {
        socket.getAndSet(null)?.close(1000, "session closed")
        context.stopService(Intent(context, MediaProjectionService::class.java))
    }

    companion object {
        private const val TAG = "CloudCtlLive"

        /** Poll the device live status; starts the grant flow when a session opens. */
        fun checkForSession(context: Context, connection: CloudConnection, gestures: RemoteGestureSink): LiveSessionController? {
            return runCatching {
                val (status, body) = PinnedHttpsTransport.request(
                    connection.baseUrl,
                    "/companion/v2/live/session",
                    connection.certificateSha256, "GET",
                    mapOf(
                        "Authorization" to "Bearer ${connection.bearerToken}",
                        "Accept" to "application/json",
                    ),
                    ByteArray(0), 10_000, 15_000,
                )
                val payload = runCatching { JSONObject(body) }.getOrNull() ?: return null
                if (status == 404) return null
                val sid = payload.optString("sessionId")
                if (status != 200 || sid.isBlank()) return null
                LiveSessionController(context, connection, gestures).also { controller ->
                    controller.activeSid = sid
                }
            }.getOrNull()
        }
    }
}

/** Gesture sink implemented by the accessibility service; never shell input. */
interface RemoteGestureSink {
    fun remoteTap(x: Double, y: Double)
    fun remoteSwipe(x1: Double, y1: Double, x2: Double, y2: Double)
}

