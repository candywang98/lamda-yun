package com.company.cloudctl.companion.live

import android.content.Context
import android.content.Intent
import android.os.SystemClock
import android.util.Log
import com.company.cloudctl.companion.network.CloudConnection
import com.company.cloudctl.companion.network.PinnedHttpsTransport
import com.company.cloudctl.companion.runtime.DeviceArbiter
import com.company.cloudctl.companion.runtime.DeviceArbiterHolder
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/**
 * Companion side of a live session (p10-live/20260913.1 + K13
 * live-capabilities/v1@20260917.1, task L11). Polls REST status, streams
 * frames with geometry metadata over the companion WS, and executes remote
 * inputs exclusively through [RemoteInputGate] (B10 arbiter + epoch +
 * frame-freshness + BLK-008 device-side unfinished-rows gate). Never uses
 * shell input.
 *
 * Lifecycle wiring (L11 requirement 1):
 *  - one MediaProjection user confirmation per session, held in the
 *    [ProjectionGrantRegistry] and handed to [MediaProjectionService] as a
 *    single-use grant (sessionId+grantId scoped: a new session can never
 *    reuse a previous session's projection token);
 *  - onStop / revoke / server CLOSED -> [stop] returns the arbiter lease,
 *    revokes the grant, and tears the capture down;
 *  - rotation -> [MediaProjectionService] resizes the virtual display and the
 *    frames from the next frameSeq carry the new geometry.
 */
class LiveSessionController(
    private val context: Context,
    private val connection: CloudConnection,
    private val gestures: RemoteGestureSink,
    private val arbiter: DeviceArbiter = DeviceArbiterHolder.get(),
    private val unfinishedTaskRows: () -> Boolean = { false },
    private val auditor: (LiveInputAudit) -> Unit = { audit ->
        Log.i(
            TAG,
            "LIVE_AUDIT event=${audit.event} sid=${audit.sessionId} seq=${audit.seq} " +
                "frameSeq=${audit.frameSeq} code=${audit.code} detail=${audit.detail}",
        )
    },
    private val clock: () -> Long = { SystemClock.elapsedRealtime() },
) {
    private val machine = LiveClientStateMachine()
    private val ledger = FrameLedger()
    private val grantRegistry = ProjectionGrantRegistry<ProjectionToken>()
    private val gate = RemoteInputGate(
        sessionId = "",
        machine = machine,
        ledger = ledger,
        arbiter = arbiter,
        unfinishedTaskRows = unfinishedTaskRows,
        auditor = auditor,
        clock = clock,
    )
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

    /** Binds the REST-discovered session id onto the audit/gate context. */
    fun bindSessionId(sid: String) {
        gate.bind(sid)
    }

    private fun ack(sid: String, granted: Boolean, resultCode: Int, data: Intent?) {
        runCatching {
            if (granted && data != null) {
                // One user confirmation per session; the grant is single-use
                // and bound to THIS session id (a later session cannot
                // consume it). authorize() throws when this session was
                // already authorized once.
                grantRegistry.authorize(sid, ProjectionToken(resultCode, data), clock())
            }
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
                machine.onOpened()
                startCapture(sid)
                connectSocket(sid)
            }
        }.onFailure { Log.w(TAG, "live ack failed", it) }
    }

    private fun startCapture(sid: String) {
        val intent = Intent(context, MediaProjectionService::class.java)
            .putExtra(MediaProjectionService.EXTRA_SESSION_ID, sid)
            .putExtra(MediaProjectionService.EXTRA_GRANT_ID, grantRegistry.grantOf(sid)?.grantId ?: -1L)
        // The projection payload (resultCode/data) is NOT put in the intent:
        // the service fetches it from the registry via the single-use
        // consume(), so a stale intent can never restart an old projection.
        MediaProjectionService.grantRegistry = grantRegistry
        MediaProjectionService.frameListener = { frame -> onFrameCaptured(frame) }
        MediaProjectionService.projectionStoppedListener = { stoppedSid, cause ->
            if (stoppedSid == activeSid) stop(cause)
        }
        context.startForegroundService(intent)
    }

    /**
     * A captured frame arrived from the projection service: stamp it with the
     * next frameSeq under its capture-time geometry (rotation-aware) and send
     * it with the K13 §3 descriptor so the operator side can aim inputs in
     * frame space. VIEWING keeps streaming: passive viewing coexists with
     * automation and never touches the arbiter.
     */
    fun onFrameCaptured(capture: CapturedFrame) {
        val geometry = runCatching {
            FrameGeometry(
                frameWidth = capture.frameWidth,
                frameHeight = capture.frameHeight,
                deviceWidth = capture.deviceWidth,
                deviceHeight = capture.deviceHeight,
                rotation = capture.rotation,
                safeArea = capture.safeArea,
            )
        }.getOrNull() ?: run {
            Log.w(TAG, "dropping frame with invalid geometry: $capture")
            return
        }
        val stamp = ledger.recordNext(geometry, clock())
        socket.get()?.send(
            JSONObject()
                .put("t", "frame")
                .put("seq", stamp.frameSeq)
                .put("jpeg", capture.jpegBase64)
                .put(
                    "geometry",
                    JSONObject()
                        .put("frameWidth", geometry.frameWidth)
                        .put("frameHeight", geometry.frameHeight)
                        .put("deviceWidth", geometry.deviceWidth)
                        .put("deviceHeight", geometry.deviceHeight)
                        .put("rotation", geometry.rotation)
                        .apply { geometry.safeArea?.let { sa -> put("safeArea", JSONObject().put("left", sa.left).put("top", sa.top).put("right", sa.right).put("bottom", sa.bottom)) } },
                )
                .toString(),
        )
    }

    fun setRemote(remote: Boolean) {
        if (remote) {
            val lease = gate.beginRemote()
            if (lease == null) {
                // The device stays VIEWING: a task session owns the device
                // (automation and remote input never run concurrently) — the
                // server remains the session-state authority and its inputs
                // will be rejected and audited here.
                Log.w(TAG, "take-control refused by device arbiter; staying VIEWING")
            }
        } else {
            gate.endRemote()
        }
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
                                stop("SERVER_CLOSED")
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
        val sid = activeSid ?: return
        val command = RemoteInputCommand(
            kind = when (message.optString("kind")) {
                "tap" -> RemoteInputKind.TAP
                "swipe" -> RemoteInputKind.SWIPE
                "text" -> RemoteInputKind.TEXT
                else -> return
            },
            seq = message.optLong("seq", 0),
            frameSeq = message.optLong("frameSeq", 0),
            x = message.optDouble("x", 0.0),
            y = message.optDouble("y", 0.0),
            x2 = message.optDouble("x2", 0.0),
            y2 = message.optDouble("y2", 0.0),
            text = if (message.has("text")) message.optString("text") else null,
        )
        when (val decision = gate.evaluate(command)) {
            is RemoteInputDecision.Approved -> {
                if (decision.command.kind == RemoteInputKind.TAP) {
                    gestures.remoteTap(decision.epoch, decision.startDx.toDouble(), decision.startDy.toDouble())
                } else {
                    gestures.remoteSwipe(
                        decision.epoch,
                        decision.startDx.toDouble(),
                        decision.startDy.toDouble(),
                        (decision.endDx ?: decision.startDx).toDouble(),
                        (decision.endDy ?: decision.startDy).toDouble(),
                    )
                }
            }
            is RemoteInputDecision.Rejected -> {
                // Already audited inside the gate. Metadata-only rejection
                // notice; the server relay mirrors these codes (K13 §4/§9).
                Log.w(
                    TAG,
                    "remote input rejected sid=$sid seq=${command.seq} " +
                        "code=${decision.rejection.code} detail=${decision.audit.detail}",
                )
            }
        }
    }

    /**
     * Session teardown: returns the arbiter lease (holder/epoch cleanup),
     * revokes the projection grant (token dead — a new session must obtain a
     * fresh user confirmation), closes the socket, and stops the capture.
     */
    fun stop(cause: String = "OPERATOR_STOP") {
        val sid = activeSid
        if (gate.leaseEpoch != null) {
            gate.terminate(cause)
        } else if (machine.state != LiveClientState.CLOSED) {
            machine.onClosed()
        }
        sid?.let { grantRegistry.revoke(it, cause, clock()) }
        socket.getAndSet(null)?.close(1000, "session closed")
        MediaProjectionService.projectionStoppedListener = null
        MediaProjectionService.frameListener = null
        MediaProjectionService.grantRegistry = null
        context.stopService(Intent(context, MediaProjectionService::class.java))
    }

    companion object {
        private const val TAG = "CloudCtlLive"

        /** Poll the device live status; starts the grant flow when a session opens. */
        fun checkForSession(
            context: Context,
            connection: CloudConnection,
            gestures: RemoteGestureSink,
            arbiter: DeviceArbiter = DeviceArbiterHolder.get(),
            unfinishedTaskRows: () -> Boolean = { false },
        ): LiveSessionController? {
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
                LiveSessionController(
                    context = context,
                    connection = connection,
                    gestures = gestures,
                    arbiter = arbiter,
                    unfinishedTaskRows = unfinishedTaskRows,
                ).also { controller ->
                    controller.activeSid = sid
                    controller.bindSessionId(sid)
                }
            }.getOrNull()
        }
    }
}

/**
 * Gesture sink implemented by the accessibility service; never shell input.
 * Coordinates are DEVICE-space (already inverse-transformed by the gate from
 * the frame space the operator aimed at) and [epoch] is the arbiter lease the
 * gate minted at take-control: the sink must present it to its own
 * UiExecutionPort / tryWrite call so the write is fenced by the same epoch
 * (a token-less write would be denied as EPOCH_STALE once the live side
 * registers its remote grant — automation/CloudCtlAccessibilityService.remoteTap
 * wiring seam, see the L11 handover).
 */
interface RemoteGestureSink {
    fun remoteTap(epoch: Long, x: Double, y: Double)

    fun remoteSwipe(epoch: Long, x1: Double, y1: Double, x2: Double, y2: Double)
}

/**
 * The MediaProjection user-confirmation payload, bound to exactly one
 * session by the [ProjectionGrantRegistry]; single-use.
 */
data class ProjectionToken(
    val resultCode: Int,
    val data: Intent,
)

/**
 * One encoded frame as produced by [MediaProjectionService]: JPEG bytes plus
 * the capture-time geometry context (K13 §3 descriptor inputs). [rotation]
 * is the encoder rotation applied for THIS frame (0 for the auto-mirroring
 * virtual display; 90/180/270 when an orientation-locked encoder is used).
 */
data class CapturedFrame(
    val jpegBase64: String,
    val frameWidth: Int,
    val frameHeight: Int,
    val deviceWidth: Int,
    val deviceHeight: Int,
    val rotation: Int,
    val safeArea: SafeAreaRect? = null,
)
