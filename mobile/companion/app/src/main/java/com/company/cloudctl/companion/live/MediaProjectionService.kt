package com.company.cloudctl.companion.live

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.IBinder
import android.util.Base64
import android.util.Log
import android.view.Display
import com.company.cloudctl.companion.MainActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.ByteArrayOutputStream

/**
 * Foreground MediaProjection capture service (p10-live/20260913.1 + K13 §6,
 * task L11). One capture per session; frames go out through the live link as
 * base64 JPEG with per-frame geometry metadata, never to disk.
 *
 * Lifecycle rules (L11 requirement 1):
 *  - the projection payload is fetched from the session-scoped
 *    [ProjectionGrantRegistry] via a SINGLE-USE consume keyed by
 *    (sessionId, grantId): a start intent without a fresh grant (replay,
 *    stale extras, another session's token) is refused outright — every new
 *    session needs its own live user confirmation;
 *  - MediaProjection.onStop (user revoke, lock-screen teardown) revokes the
 *    grant and notifies the controller, which closes the session (K13 §6:
 *    restart/teardown is terminal, no silent resume);
 *  - rotation resizes the virtual display (old ImageReader closed and
 *    replaced) WITHOUT re-authorization: the grant survives in-flight
 *    resizes and frames from the next frameSeq carry the new geometry;
 *  - teardown recycles resources in order: drain+close the ImageReader,
 *    release the VirtualDisplay, stop the MediaProjection.
 */
class MediaProjectionService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val projectionLock = Any()
    private var projection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var reader: ImageReader? = null
    private var frameSender: ((String) -> Unit)? = null
    private var remoteMode = false
    private val params = FrameParams.DEFAULT

    // Capture-time geometry snapshot; updated on resize, read per frame.
    @Volatile
    private var captureWidth = 0
    @Volatile
    private var captureHeight = 0
    @Volatile
    private var deviceWidth = 0
    @Volatile
    private var deviceHeight = 0
    @Volatile
    private var captureRotation = 0

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopCapture(revokeCause = ProjectionGrantRegistry.CAUSE_OPERATOR_STOP)
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_RESIZE -> {
                // Rotation: rebuild the capture surface at the new metrics;
                // the projection itself (and its grant) stays alive.
                resizeCapture(
                    deviceWidth = intent.getIntExtra(EXTRA_DEVICE_WIDTH, this.deviceWidth),
                    deviceHeight = intent.getIntExtra(EXTRA_DEVICE_HEIGHT, this.deviceHeight),
                    rotation = intent.getIntExtra(EXTRA_ROTATION, captureRotation),
                )
                return START_NOT_STICKY
            }
            else -> {
                val sessionId = intent?.getStringExtra(EXTRA_SESSION_ID)
                val grantId = intent?.getLongExtra(EXTRA_GRANT_ID, -1L) ?: -1L
                if (sessionId.isNullOrBlank() || grantId <= 0) {
                    Log.w(TAG, "projection start refused: no session/grant scope")
                    stopSelf()
                    return START_NOT_STICKY
                }
                val grants = grantRegistry
                if (grants == null) {
                    Log.w(TAG, "projection start refused: no registry attached")
                    stopSelf()
                    return START_NOT_STICKY
                }
                // Single-use consume: session-scoped, one-shot. A replayed or
                // stale intent (old session, spent token, mismatched grant
                // id) never reaches getMediaProjection().
                val grant = synchronized(projectionLock) {
                    if (projection != null) {
                        Log.w(TAG, "projection start refused: capture already active")
                        return@synchronized null
                    }
                    val pending = grants.grantOf(sessionId)
                    if (pending == null ||
                        pending.grantId != grantId ||
                        pending.state != ProjectionGrantRegistry.GrantState.AUTHORIZED
                    ) {
                        Log.w(
                            TAG,
                            "projection start refused: stale or spent token for session=$sessionId " +
                                "grantId=$grantId pending=${pending?.grantId}/${pending?.state}",
                        )
                        return@synchronized null
                    }
                    grants.consume(sessionId, System.currentTimeMillis())
                }
                if (grant == null) {
                    stopSelf()
                    return START_NOT_STICKY
                }
                startForegroundCompat()
                startCapture(sessionId, grant.payload.resultCode, grant.payload.data)
                return START_NOT_STICKY
            }
        }
    }

    fun attach(sender: (String) -> Unit, remote: Boolean) {
        frameSender = sender
        remoteMode = remote
    }

    fun setRemote(remote: Boolean) {
        remoteMode = remote
    }

    private fun startForegroundCompat() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "实时观看", NotificationManager.IMPORTANCE_LOW),
        )
        val content = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE,
        )
        val notification: Notification = Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_menu_camera)
            .setContentTitle("云控实时投屏中")
            .setContentText("操作员正在观看此设备屏幕")
            .setContentIntent(content)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun startCapture(sessionId: String, resultCode: Int, data: android.content.Intent) {
        activeSessionId = sessionId
        val manager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        val metrics = resources.displayMetrics
        deviceWidth = metrics.widthPixels
        deviceHeight = metrics.heightPixels
        captureRotation = currentRotation()
        val (targetWidth, targetHeight) = params.scale(deviceWidth, deviceHeight)
        captureWidth = targetWidth
        captureHeight = targetHeight
        val projectionInstance = manager.getMediaProjection(resultCode, data)
        projection = projectionInstance
        projectionInstance.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() {
                // User revoked / system tore the projection down (also covers
                // lock-screen teardown): the grant dies with it — terminal,
                // never resumed; a new session needs a new confirmation.
                Log.w(TAG, "MediaProjection onStop sid=$sessionId")
                grantRegistry?.revoke(sessionId, ProjectionGrantRegistry.CAUSE_USER_REVOKED, System.currentTimeMillis())
                stopCapture(revokeCause = null) // already revoked above
                projectionStoppedListener?.invoke(sessionId, ProjectionGrantRegistry.CAUSE_USER_REVOKED)
                stopSelf()
            }
        }, null)
        reader = ImageReader.newInstance(targetWidth, targetHeight, PixelFormat.RGBA_8888, 2)
        virtualDisplay = projectionInstance.createVirtualDisplay(
            "cloudctl-live", targetWidth, targetHeight, metrics.densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            reader!!.surface, null, null,
        )
        scope.launch { captureLoop(sessionId) }
    }

    /**
     * Rotation / resolution change: the old reader is drained and closed and
     * the virtual display is rebuilt at the new size; the MediaProjection
     * (and its authorization) is intentionally left running. Frames from the
     * next capture carry the new geometry via the per-frame metadata.
     */
    private fun resizeCapture(deviceWidth: Int, deviceHeight: Int, rotation: Int) {
        synchronized(projectionLock) {
            val projectionInstance = projection ?: return
            if (deviceWidth <= 0 || deviceHeight <= 0) return
            if (deviceWidth == this.deviceWidth && deviceHeight == this.deviceHeight && rotation == captureRotation) {
                return
            }
            Log.i(TAG, "live resize ${this.deviceWidth}x${this.deviceHeight}@${captureRotation} -> ${deviceWidth}x${deviceHeight}@$rotation")
            closeReaderLocked()
            runCatching { virtualDisplay?.release() }
            virtualDisplay = null
            this.deviceWidth = deviceWidth
            this.deviceHeight = deviceHeight
            captureRotation = rotation
            val (targetWidth, targetHeight) = params.scale(deviceWidth, deviceHeight)
            captureWidth = targetWidth
            captureHeight = targetHeight
            reader = ImageReader.newInstance(targetWidth, targetHeight, PixelFormat.RGBA_8888, 2)
            virtualDisplay = projectionInstance.createVirtualDisplay(
                "cloudctl-live", targetWidth, targetHeight, resources.displayMetrics.densityDpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                reader!!.surface, null, null,
            )
        }
    }

    private fun currentRotation(): Int {
        val display: Display? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            this.display
        } else {
            @Suppress("DEPRECATION")
            (getSystemService(Context.WINDOW_SERVICE) as android.view.WindowManager).defaultDisplay
        }
        @Suppress("DEPRECATION")
        return when (display?.rotation) {
            android.view.Surface.ROTATION_90 -> 90
            android.view.Surface.ROTATION_180 -> 180
            android.view.Surface.ROTATION_270 -> 270
            else -> 0
        }
    }

    private suspend fun captureLoop(sessionId: String) {
        while (scope.isActive) {
            val image: Image? = try {
                reader?.acquireLatestImage()
            } catch (error: Exception) {
                Log.w(TAG, "frame acquire failed", error)
                null
            }
            if (image != null) {
                val encoded = image.toEncodedFrame(params)
                image.close()
                if (encoded != null) {
                    val frame = CapturedFrame(
                        jpegBase64 = Base64.encodeToString(encoded.jpeg, Base64.NO_WRAP),
                        frameWidth = encoded.width,
                        frameHeight = encoded.height,
                        deviceWidth = deviceWidth,
                        deviceHeight = deviceHeight,
                        // Auto-mirroring display: the buffer is already in the
                        // current orientation, so the encoder rotation is 0.
                        // An orientation-locked encoder would report its
                        // 90/180/270 here; the frame-geometry kernel on the
                        // controller side handles all four.
                        rotation = 0,
                    )
                    frameListener?.invoke(frame) ?: frameSender?.invoke(frame.jpegBase64)
                }
            }
            delay(params.intervalMs(remoteMode))
        }
    }

    private data class EncodedFrame(val jpeg: ByteArray, val width: Int, val height: Int)

    private fun Image.toEncodedFrame(params: FrameParams): EncodedFrame? = runCatching {
        val plane = planes[0]
        val rowStride = plane.rowStride
        val pixelStride = plane.pixelStride
        val bitmapWidth = minOf(width, (rowStride / pixelStride).toInt().coerceAtLeast(1))
        val bitmap = Bitmap.createBitmap(bitmapWidth, height, Bitmap.Config.ARGB_8888)
        bitmap.copyPixelsFromBuffer(plane.buffer)
        val (targetWidth, targetHeight) = params.scale(bitmap.width, bitmap.height)
        val scaled = if (targetWidth != bitmap.width) {
            Bitmap.createScaledBitmap(bitmap, targetWidth, targetHeight, true).also {
                if (it !== bitmap) bitmap.recycle()
            }
        } else {
            bitmap
        }
        val output = ByteArrayOutputStream()
        scaled.compress(Bitmap.CompressFormat.JPEG, params.jpegQuality, output)
        scaled.recycle()
        EncodedFrame(output.toByteArray(), width = scaled.width, height = scaled.height)
    }.getOrNull()

    /** Drains and closes the ImageReader (recycle path); lock held by caller. */
    private fun closeReaderLocked() {
        val current = reader ?: return
        runCatching {
            while (true) current.acquireLatestImage()?.close() ?: break
        }
        runCatching { current.close() }
        reader = null
    }

    private fun stopCapture(revokeCause: String?) {
        synchronized(projectionLock) {
            // Ordered teardown: reader (drained+closed) -> virtual display ->
            // projection; the revocation cause only fires once per grant.
            closeReaderLocked()
            runCatching { virtualDisplay?.release() }
            virtualDisplay = null
            val projectionInstance = projection
            projection = null
            revokeCause?.let { cause ->
                activeSessionId?.let { sid ->
                    grantRegistry?.revoke(sid, cause, System.currentTimeMillis())
                }
            }
            runCatching { projectionInstance?.stop() }
        }
    }

    override fun onDestroy() {
        stopCapture(revokeCause = ProjectionGrantRegistry.CAUSE_SERVICE_CRASH)
        scope.cancel()
        super.onDestroy()
    }

    companion object {
        private const val TAG = "CloudCtlLive"
        private const val CHANNEL_ID = "cloudctl_live"
        private const val NOTIFICATION_ID = 4201

        // Process-wide glue to the owning LiveSessionController (one live
        // session per process). The controller attaches these before starting
        // the service and detaches on stop.
        @Volatile
        var grantRegistry: ProjectionGrantRegistry<ProjectionToken>? = null

        @Volatile
        var frameListener: ((CapturedFrame) -> Unit)? = null

        @Volatile
        var projectionStoppedListener: ((sessionId: String, cause: String) -> Unit)? = null

        @Volatile
        private var activeSessionId: String? = null

        const val ACTION_STOP = "com.company.cloudctl.companion.live.STOP"
        const val ACTION_RESIZE = "com.company.cloudctl.companion.live.RESIZE"
        const val EXTRA_SESSION_ID = "session_id"
        const val EXTRA_GRANT_ID = "grant_id"
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_RESULT_DATA = "result_data"
        const val EXTRA_DEVICE_WIDTH = "device_width"
        const val EXTRA_DEVICE_HEIGHT = "device_height"
        const val EXTRA_ROTATION = "rotation"
    }
}
