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
import com.company.cloudctl.companion.MainActivity
import com.company.cloudctl.companion.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.ByteArrayOutputStream

/**
 * Foreground MediaProjection capture service (p10-live/20260913.1). One capture
 * per session; frames go out through the LiveLink as base64 JPEG, never to disk.
 */
class MediaProjectionService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var projection: MediaProjection? = null
    private var display: VirtualDisplay? = null
    private var reader: ImageReader? = null
    private var frameSender: ((String) -> Unit)? = null
    private var remoteMode = false
    private val params = FrameParams.DEFAULT

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopCapture()
                stopSelf()
                return START_NOT_STICKY
            }
            else -> {
                val resultCode = intent?.getIntExtra(EXTRA_RESULT_CODE, 0) ?: 0
                @Suppress("DEPRECATION")
                val data = intent?.getParcelableExtra<android.content.Intent>(EXTRA_RESULT_DATA)
                if (data == null) {
                    stopSelf()
                    return START_NOT_STICKY
                }
                startForegroundCompat()
                startCapture(resultCode, data)
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

    private fun startCapture(resultCode: Int, data: android.content.Intent) {
        val metrics = resources.displayMetrics
        val width = metrics.widthPixels
        val height = metrics.heightPixels
        val (targetWidth, targetHeight) = params.scale(width, height)
        val manager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        projection = manager.getMediaProjection(resultCode, data).also { projection ->
            projection.registerCallback(object : MediaProjection.Callback() {
                override fun onStop() {
                    stopCapture()
                    stopSelf()
                }
            }, null)
            reader = ImageReader.newInstance(targetWidth, targetHeight, PixelFormat.RGBA_8888, 2)
            display = projection.createVirtualDisplay(
                "cloudctl-live", targetWidth, targetHeight, metrics.densityDpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                reader!!.surface, null, null,
            )
            scope.launch { captureLoop() }
        }
    }

    private suspend fun captureLoop() {
        while (scope.isActive) {
            val image: Image? = try {
                reader?.acquireLatestImage()
            } catch (error: Exception) {
                Log.w(TAG, "frame acquire failed", error)
                null
            }
            if (image != null) {
                val jpeg = image.toJpeg(params)
                image.close()
                if (jpeg != null) {
                    val encoded = Base64.encodeToString(jpeg, Base64.NO_WRAP)
                    frameSender?.invoke(encoded)
                }
            }
            delay(params.intervalMs(remoteMode))
        }
    }

    private fun Image.toJpeg(params: FrameParams): ByteArray? = runCatching {
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
        output.toByteArray()
    }.getOrNull()

    private fun stopCapture() {
        runCatching { reader?.close() }
        runCatching { display?.release() }
        runCatching { projection?.stop() }
        reader = null
        display = null
        projection = null
    }

    override fun onDestroy() {
        stopCapture()
        scope.cancel()
        super.onDestroy()
    }

    companion object {
        private const val TAG = "CloudCtlLive"
        private const val CHANNEL_ID = "cloudctl_live"
        private const val NOTIFICATION_ID = 4201
        const val ACTION_STOP = "com.company.cloudctl.companion.live.STOP"
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_RESULT_DATA = "result_data"
    }
}
