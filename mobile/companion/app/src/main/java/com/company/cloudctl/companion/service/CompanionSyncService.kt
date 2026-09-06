package com.company.cloudctl.companion.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import android.util.Base64
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import com.company.cloudctl.companion.R
import com.company.cloudctl.companion.automation.AutomationTaskParser
import com.company.cloudctl.companion.automation.CloudCtlAccessibilityService
import com.company.cloudctl.companion.data.AutomationStore
import com.company.cloudctl.companion.data.RuntimeStatusStore
import com.company.cloudctl.companion.data.MediaDeliveryCoordinator
import com.company.cloudctl.companion.device.LocalHealthCollector
import com.company.cloudctl.companion.model.AuthorizedTaskState
import com.company.cloudctl.companion.network.CloudConnection
import com.company.cloudctl.companion.network.ClaimedTask
import com.company.cloudctl.companion.network.CloudHttpException
import com.company.cloudctl.companion.network.CloudTaskClient
import com.company.cloudctl.companion.network.PreviewGrant
import com.company.cloudctl.companion.network.DeliveryFailureAction
import com.company.cloudctl.companion.network.OutboxRetryPolicy
import com.company.cloudctl.companion.network.NetworkAvailability
import com.company.cloudctl.companion.security.SecretStore
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import java.io.IOException
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicInteger

class CompanionSyncService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private lateinit var store: AutomationStore
    private lateinit var runtimeStatus: RuntimeStatusStore
    private lateinit var networkAvailability: NetworkAvailability
    private lateinit var mediaDeliveryCoordinator: MediaDeliveryCoordinator
    private var syncJob: Job? = null
    private var presenceJob: Job? = null

    override fun onCreate() {
        super.onCreate()
        store = AutomationStore(this)
        runtimeStatus = RuntimeStatusStore(this)
        networkAvailability = NetworkAvailability(this)
        mediaDeliveryCoordinator = MediaDeliveryCoordinator(this)
        store.recoverInterruptedRuns()
        createNotificationChannel()
        ServiceCompat.startForeground(
            this,
            NOTIFICATION_ID,
            NotificationCompat.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_launcher_foreground)
                .setContentTitle("CloudCtl Companion")
                .setContentText("Secure task synchronization is active")
                .setOngoing(true)
                .build(),
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            } else {
                0
            },
        )
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (syncJob?.isActive != true) syncJob = scope.launch { syncLoop() }
        if (presenceJob?.isActive != true) presenceJob = scope.launch { presenceLoop() }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        scope.cancel()
        store.close()
        super.onDestroy()
    }

    override fun onTimeout(startId: Int, fgsType: Int) {
        CompanionServiceStarter.scheduleRestartIfBound(this)
        stopSelf(startId)
    }

    private suspend fun presenceLoop() {
        android.util.Log.i("CompanionSync", "presenceLoop starting")
        val configured = loadConnection()
        if (configured == null) {
            android.util.Log.e("CompanionSync", "loadConnection returned null - binding not found or token missing")
            return
        }
        android.util.Log.i("CompanionSync", "Connection loaded, starting heartbeat loop")
        val client = CloudTaskClient(configured.first)
        val healthCollector = LocalHealthCollector(this)
        val retryPolicy = SyncRetryPolicy(
            initialDelayMillis = HEARTBEAT_RETRY_INITIAL_MILLIS,
            maximumDelayMillis = HEARTBEAT_RETRY_MAXIMUM_MILLIS,
        )
        while (scope.isActive) {
            try {
                if (networkAvailability.isValidated()) {
                    android.util.Log.d("CompanionSync", "Network validated, sending heartbeat")
                    val health = healthCollector.collect()
                    val payload = JSONObject()
                        .put("companionVersion", health.companionVersion)
                        .put("androidVersion", Build.VERSION.RELEASE)
                        .put("accessibilityEnabled", accessibilityEnabled())
                        .put("runnerState", runnerState())
                    val healthJson = JSONObject()
                        .put("batteryPercent", health.batteryPercent)
                        .put("charging", health.charging)
                        .put("network", health.network)
                        .put("freeStorageBytes", health.freeStorageBytes)
                    health.temperatureCelsius?.let { healthJson.put("temperatureCelsius", it.toDouble()) }
                    payload.put("health", healthJson)
                    // batteryOptimizationIgnored 字段已从 API schema 中移除
                    android.util.Log.d("CompanionSync", "Sending heartbeat payload: $payload")
                    val heartbeat = withContext(Dispatchers.IO) { client.deviceHeartbeat(payload) }
                    android.util.Log.i("CompanionSync", "Heartbeat successful")
                    runtimeStatus.markPresence(true)
                    retryPolicy.reset()
                    val grant = PreviewGrant.fromHeartbeat(heartbeat)
                    if (grant != null) {
                        uploadPreviewFrame(client, grant)
                        delay(grant.captureIntervalMs)
                        continue
                    }
                } else {
                    android.util.Log.w("CompanionSync", "Network not validated, skipping heartbeat")
                    runtimeStatus.markPresence(false)
                }
                delay(DEVICE_HEARTBEAT_INTERVAL_MILLIS)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: CloudHttpException) {
                android.util.Log.e("CompanionSync", "HTTP error in heartbeat: ${error.message}, status: ${error.status}, body: ${error.responseBody}, auth rejected: ${error.authenticationRejected}")
                runtimeStatus.markPresence(false)
                if (error.authenticationRejected) return
                delay(retryPolicy.nextDelayMillis())
            } catch (error: IOException) {
                android.util.Log.e("CompanionSync", "IO error in heartbeat: ${error.message}")
                runtimeStatus.markPresence(false)
                delay(retryPolicy.nextDelayMillis())
            } catch (error: Exception) {
                android.util.Log.e("CompanionSync", "Unexpected error in heartbeat: ${error.message}", error)
                runtimeStatus.markPresence(false)
                delay(retryPolicy.nextDelayMillis())
            }
        }
    }

    private suspend fun uploadPreviewFrame(client: CloudTaskClient, grant: PreviewGrant) {
        val service = CloudCtlAccessibilityService.active ?: return
        val frame = runCatching { service.capturePreviewJpeg() }.getOrNull() ?: return
        val digest = MessageDigest.getInstance("SHA-256").digest(frame.jpeg)
            .joinToString("") { "%02x".format(it) }
        val payload = JSONObject()
            .put("sessionId", grant.sessionId)
            .put("contentType", "image/jpeg")
            .put("sha256", digest)
            .put("width", frame.width)
            .put("height", frame.height)
            .put("imageBase64", Base64.encodeToString(frame.jpeg, Base64.NO_WRAP))
        runCatching { withContext(Dispatchers.IO) { client.uploadPreview(payload) } }
    }

    private fun runnerState(): String {
        val task = runtimeStatus.snapshot().task
        return when (task?.state) {
            AuthorizedTaskState.Running,
            AuthorizedTaskState.WaitingConfirmation,
            AuthorizedTaskState.Stopping,
            -> "RUNNING"
            else -> "IDLE"
        }
    }

    private fun accessibilityEnabled(): Boolean {
        val enabled = Settings.Secure.getString(
            contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
        ).orEmpty()
        val service = "$packageName/$packageName.automation.CloudCtlAccessibilityService"
        return enabled.split(':').any { it.equals(service, ignoreCase = true) }
    }

    private suspend fun syncLoop() {
        val configured = loadConnection() ?: run {
            stopSelf()
            return
        }
        val client = CloudTaskClient(configured.first)
        val retryPolicy = SyncRetryPolicy()
        while (scope.isActive) {
            var claimed: ClaimedTask? = null
            try {
                if (networkAvailability.isValidated()) {
                    flushOutbox(client)
                    claimed = withContext(Dispatchers.IO) { client.claim() }
                }
                if (claimed != null) {
                    val task = try {
                        AutomationTaskParser.parse(claimed.taskPayload)
                    } catch (_: Exception) {
                        store.enqueueTask(
                            claimed.taskId,
                            claimed.taskPayload,
                            claimed.leaseId,
                            claimed.lastSequence,
                        )
                        store.finish(claimed.taskId, false, "TASK_CONTRACT_REJECTED")
                        runtimeStatus.updateTask(
                            claimed.taskId,
                            AuthorizedTaskState.Failed,
                            "任务指令校验未通过",
                            "TASK_CONTRACT_REJECTED",
                        )
                        continue
                    }
                    require(task.deviceId == configured.second && claimed.deviceId == configured.second) {
                        "Task belongs to another device"
                    }
                    store.enqueueTask(task.taskId, claimed.taskPayload, claimed.leaseId, claimed.lastSequence)
                    runtimeStatus.updateTask(
                        task.taskId,
                        AuthorizedTaskState.Queued,
                        "已收到云端任务",
                        "TASK_QUEUED",
                    )
                }
                val executed = runNext(client)
                retryPolicy.reset()
                if (!executed) delay(if (claimed == null) IDLE_POLL_INTERVAL_MILLIS else 100L)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: CloudHttpException) {
                if (error.authenticationRejected || !error.retryable) {
                    stopSelf()
                    return
                }
                delay(retryPolicy.nextDelayMillis())
            } catch (_: IOException) {
                delay(retryPolicy.nextDelayMillis())
            } catch (_: Exception) {
                delay(retryPolicy.nextDelayMillis())
            }
        }
    }

    private suspend fun runNext(
        client: CloudTaskClient,
    ): Boolean {
        val pending = store.claimNext() ?: return false
        val task = runCatching { AutomationTaskParser.parse(pending.payload) }
            .getOrElse {
                store.finish(pending.taskId, false, "TASK_CONTRACT_REJECTED")
                return true
            }
        runCatching { JSONObject(pending.payload).optJSONObject("mediaDelivery") }
            .getOrNull()
            ?.let { media ->
                val deliveryId = media.optString("deliveryId")
                val values = media.optJSONArray("assetIds")
                require(deliveryId.isNotBlank() && values != null && values.length() in 1..50) {
                    "MEDIA_DELIVERY_CONTRACT_REJECTED"
                }
                val assetIds = List(values.length()) { index -> values.getString(index) }
                require(assetIds.all { it.matches(Regex("^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")) }) {
                    "MEDIA_DELIVERY_CONTRACT_REJECTED"
                }
                val configured = loadConnection() ?: error("Cloud connection unavailable")
                runtimeStatus.updateTask(task.taskId, AuthorizedTaskState.Running, "正在下载任务素材", "MEDIA_DOWNLOAD_STARTED")
                withContext(Dispatchers.IO) {
                    mediaDeliveryCoordinator.deliver(configured.first, deliveryId, assetIds)
                }
                runtimeStatus.updateTask(task.taskId, AuthorizedTaskState.Running, "任务素材已校验", "MEDIA_DOWNLOAD_SUCCEEDED")
            }
        val service = CloudCtlAccessibilityService.active
        if (service == null) {
            store.finish(task.taskId, false, "ACCESSIBILITY_NOT_ENABLED")
            runtimeStatus.updateTask(
                task.taskId,
                AuthorizedTaskState.Failed,
                "无障碍服务未启用",
                "ACCESSIBILITY_NOT_ENABLED",
            )
            return true
        }
        try {
            runtimeStatus.updateTask(
                task.taskId,
                AuthorizedTaskState.Running,
                "正在启动本地执行器",
                "TASK_STARTED",
            )
            sendInitialHeartbeat(client, task.taskId, pending.leaseId)
            coroutineScope {
                val currentStep = AtomicInteger(-1)
                val heartbeatJob = launch(Dispatchers.IO) {
                    val heartbeatRetry = SyncRetryPolicy(
                        initialDelayMillis = HEARTBEAT_RETRY_INITIAL_MILLIS,
                        maximumDelayMillis = HEARTBEAT_RETRY_MAXIMUM_MILLIS,
                    )
                    while (isActive) {
                        delay(HEARTBEAT_INTERVAL_MILLIS)
                        var delivered = false
                        while (isActive && !delivered) {
                            try {
                                networkAvailability.awaitValidated()
                                client.heartbeat(
                                    task.taskId,
                                    pending.leaseId,
                                    currentStep.get().takeIf { it >= 0 },
                                )
                                heartbeatRetry.reset()
                                delivered = true
                            } catch (error: CloudHttpException) {
                                if (!error.retryable) throw error
                                delay(heartbeatRetry.nextDelayMillis())
                            } catch (_: IOException) {
                                delay(heartbeatRetry.nextDelayMillis())
                            }
                        }
                    }
                }
                try {
                    withTimeout(task.maxRunSeconds * 1_000L) {
                        service.execute(task) { step, state ->
                            val stepIndex = task.steps.indexOf(step)
                            currentStep.set(stepIndex)
                            store.recordStepEvent(
                                taskId = task.taskId,
                                stepId = step.stepId,
                                state = state,
                                detailCode = "STEP_$state",
                                eventType = if (state == "STARTED") "STEP_STARTED" else "STEP_SUCCEEDED",
                                stepIndex = stepIndex,
                                payload = JSONObject().put("detailCode", "STEP_$state"),
                            )
                            runtimeStatus.updateTask(
                                task.taskId,
                                AuthorizedTaskState.Running,
                                "${step.stepId}: $state",
                                "STEP_$state",
                                step.stepId,
                            )
                        }
                    }
                } finally {
                    heartbeatJob.cancelAndJoin()
                }
            }
            store.finish(task.taskId, true)
            runtimeStatus.updateTask(
                task.taskId,
                AuthorizedTaskState.Succeeded,
                "本地任务已完成",
                "TASK_SUCCEEDED",
            )
        } catch (_: Exception) {
            store.finish(task.taskId, false)
            runtimeStatus.updateTask(
                task.taskId,
                AuthorizedTaskState.Failed,
                "本地任务已安全终止",
                "TASK_EXECUTION_FAILED",
            )
        }
        return true
    }

    private suspend fun flushOutbox(client: CloudTaskClient) {
        for (outbox in store.pendingEvents()) {
            try {
                withContext(Dispatchers.IO) { client.post(outbox.path, outbox.payload) }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: CloudHttpException) {
                when (OutboxRetryPolicy.classify(error)) {
                    DeliveryFailureAction.ACCEPT_AS_DELIVERED -> store.markDelivered(outbox.id)
                    DeliveryFailureAction.PERMANENT_REJECTION -> {
                        store.markPermanentlyRejected(outbox.id, "HTTP_${error.status}")
                        return
                    }
                    DeliveryFailureAction.RETRY -> {
                        store.recordDeliveryFailure(
                            outbox.id,
                            "HTTP_${error.status}",
                            OutboxRetryPolicy.nextAttemptAt(outbox.id, outbox.attemptCount + 1),
                        )
                        return
                    }
                }
                continue
            } catch (error: Exception) {
                store.recordDeliveryFailure(
                    outbox.id,
                    error.javaClass.simpleName,
                    OutboxRetryPolicy.nextAttemptAt(outbox.id, outbox.attemptCount + 1),
                )
                return
            }
            store.markDelivered(outbox.id)
        }
    }

    private suspend fun sendInitialHeartbeat(
        client: CloudTaskClient,
        taskId: String,
        leaseId: String,
    ) {
        try {
            withContext(Dispatchers.IO) { client.heartbeat(taskId, leaseId, null) }
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: CloudHttpException) {
            if (!error.retryable) throw error
        } catch (_: IOException) {
            // A transient cloud outage must not roll back an already-started local task.
            // Ordered step events and the terminal result remain durable in the outbox.
        }
    }

    private fun loadConnection(): Pair<CloudConnection, String>? {
        val binding = getSharedPreferences("cloudctl_binding", MODE_PRIVATE)
        val encoded = binding.getString("binding", null) ?: return null
        val value = runCatching { JSONObject(encoded) }.getOrNull() ?: return null
        val cloudUrl = value.optString("cloudUrl").takeIf(String::isNotBlank) ?: return null
        val token = SecretStore(this).get("binding_token") ?: return null
        return CloudConnection(
            baseUrl = cloudUrl,
            bearerToken = token,
            certificateSha256 = value.getString("certificateSha256"),
        ) to value.getString("deviceId")
    }

    private fun createNotificationChannel() {
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Cloud task execution", NotificationManager.IMPORTANCE_LOW),
        )
    }

    private companion object {
        const val CHANNEL_ID = "cloudctl_sync"
        const val NOTIFICATION_ID = 1001
        const val HEARTBEAT_INTERVAL_MILLIS = 20_000L
        const val DEVICE_HEARTBEAT_INTERVAL_MILLIS = 20_000L
        const val HEARTBEAT_RETRY_INITIAL_MILLIS = 1_000L
        const val HEARTBEAT_RETRY_MAXIMUM_MILLIS = 10_000L
        const val IDLE_POLL_INTERVAL_MILLIS = 2_000L
    }
}
