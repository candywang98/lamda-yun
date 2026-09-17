package com.company.cloudctl.companion.service

import android.app.KeyguardManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Environment
import android.os.IBinder
import android.os.StatFs
import android.provider.Settings
import android.util.Base64
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import com.company.cloudctl.companion.BuildConfig
import com.company.cloudctl.companion.R
import com.company.cloudctl.companion.automation.AutomationTask
import com.company.cloudctl.companion.automation.AutomationStep
import com.company.cloudctl.companion.automation.CommitGate
import com.company.cloudctl.companion.automation.AutomationTaskParser
import com.company.cloudctl.companion.automation.BuiltinRecipes
import com.company.cloudctl.companion.automation.ClaimedTaskInterpreter
import com.company.cloudctl.companion.automation.CloudCtlAccessibilityService
import com.company.cloudctl.companion.automation.CommandV1
import com.company.cloudctl.companion.automation.ExecutionControl
import com.company.cloudctl.companion.automation.ExecutorFailure
import com.company.cloudctl.companion.automation.OrderDirection
import com.company.cloudctl.companion.automation.OrderReporter
import com.company.cloudctl.companion.automation.OrderScreensReporter
import com.company.cloudctl.companion.features.xianyu.orders.OrderCheckpoint
import com.company.cloudctl.companion.features.xianyu.orders.OrderPageReading
import com.company.cloudctl.companion.automation.RecipeEngine
import com.company.cloudctl.companion.automation.RecipePackage
import com.company.cloudctl.companion.automation.ResumeValidator
import com.company.cloudctl.companion.automation.TargetLocatorRegistry
import com.company.cloudctl.companion.automation.TaskPausedException
import com.company.cloudctl.companion.automation.DestructiveClickGate
import com.company.cloudctl.companion.automation.XianyuMaintenanceLayout
import com.company.cloudctl.companion.control.CapabilityProbe
import com.company.cloudctl.companion.control.ControlEvent
import com.company.cloudctl.companion.control.ControlLoopOrchestrator
import com.company.cloudctl.companion.control.ControlPlaneJson
import com.company.cloudctl.companion.control.ControlStateStore
import com.company.cloudctl.companion.control.ControlSyncClient
import com.company.cloudctl.companion.control.PinnedControlPlaneTransport
import com.company.cloudctl.companion.control.SuspectOrphanedPolicy
import com.company.cloudctl.companion.data.AutomationStore
import com.company.cloudctl.companion.im.DutyController
import com.company.cloudctl.companion.im.ImMonitor
import com.company.cloudctl.companion.data.PendingTask
import com.company.cloudctl.companion.data.RuntimeStatusStore
import com.company.cloudctl.companion.data.MediaDeliveryCoordinator
import com.company.cloudctl.companion.device.LocalHealthCollector
import com.company.cloudctl.companion.model.AuthorizedTaskState
import com.company.cloudctl.companion.network.CloudConnection
import com.company.cloudctl.companion.network.ClaimedTask
import com.company.cloudctl.companion.network.CloudHttpException
import com.company.cloudctl.companion.network.CloudTaskClient
import com.company.cloudctl.companion.network.TaskHeartbeat
import com.company.cloudctl.companion.network.buildOrdersBatchPayload
import com.company.cloudctl.companion.network.buildOrdersScreenPayload
import com.company.cloudctl.companion.network.ORDER_SCREENS_SCHEMA_VERSION
import com.company.cloudctl.companion.network.parseOrdersBatchResponse
import com.company.cloudctl.companion.network.PreviewGrant
import com.company.cloudctl.companion.network.ResumeCommand
import com.company.cloudctl.companion.network.DeliveryFailureAction
import com.company.cloudctl.companion.network.OutboxRetryPolicy
import com.company.cloudctl.companion.network.NetworkAvailability
import com.company.cloudctl.companion.runtime.DeviceArbiter
import com.company.cloudctl.companion.runtime.DeviceArbiterHolder
import com.company.cloudctl.companion.runtime.ReleaseBoundary
import com.company.cloudctl.companion.runtime.TaskSession
import com.company.cloudctl.companion.runtime.UiWriter
import com.company.cloudctl.companion.security.SecretStore
import com.company.cloudctl.companion.updates.RecipePackageManager
import com.company.cloudctl.companion.updates.RecipeLifecycle
import com.company.cloudctl.companion.updates.RecipeDownload
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicInteger

import com.company.cloudctl.companion.network.PinnedControlledActionLedger

internal fun hasMaintenanceDestructiveConfirm(task: AutomationTask): Boolean = task.steps.any { step ->
    (step is AutomationStep.TapLayout &&
        step.layoutAction in XianyuMaintenanceLayout.GATED_DESTRUCTIVE_CONFIRM_ACTIONS) ||
        (step is AutomationStep.Tap &&
            step.locatorRef == XianyuMaintenanceCommitGate.DELETE_CONFIRM_LOCATOR)
}

class CompanionSyncService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    // B10 single-writer seam: the process-wide arbiter owns the device write
    // lease. A task session is minted at the execution boundary (fresh-claim
    // heartbeat confirmed) and returned at a safe boundary in every finally;
    // the fencing token is re-checked before every task write.
    private val deviceArbiter: DeviceArbiter get() = DeviceArbiterHolder.get()

    private lateinit var recipes: RecipeLifecycle
    private lateinit var store: AutomationStore
    private lateinit var runtimeStatus: RuntimeStatusStore
    private lateinit var networkAvailability: NetworkAvailability
    private lateinit var mediaDeliveryCoordinator: MediaDeliveryCoordinator
    private var syncJob: Job? = null
    private var presenceJob: Job? = null
    private var outboxJob: Job? = null
    @Volatile
    private var pendingResume: ResumeCommand? = null

    // B17 control plane: shared between the sync loop (cursor catch-up) and
    // the presence loop (heartbeat watermark / inline events, §2.3). Built
    // lazily once a binding exists; [ControlStateStore] owns all durable state.
    @Volatile
    private var controlRuntime: ControlRuntime? = null
    @Volatile
    private var suspectForceSnapshot = false
    @Volatile
    private var suspectActive = false

    private class ControlRuntime(
        val state: ControlStateStore,
        val client: ControlSyncClient,
        val orchestrator: ControlLoopOrchestrator,
    )

    // im-live slice 2, gap 2: corrects placeholder notification bodies with the
    // real conversation text once a reply task leaves the chat page open.
    private val imBodyEnricher = com.company.cloudctl.companion.im.ImBodyEnricher(
        deviceId = { loadConnection()?.second },
    )

    override fun onCreate() {
        super.onCreate()
        store = AutomationStore(this)
        runtimeStatus = RuntimeStatusStore(this)
        networkAvailability = NetworkAvailability(this)
        mediaDeliveryCoordinator = MediaDeliveryCoordinator(this)
        store.recoverInterruptedRuns()
        // B17 startup capability self-check (CAP_*); best-effort, never gates startup.
        runCatching { runtimeStatus.updateCapabilities(CapabilityProbe.production(this).probe()) }
            .onFailure { android.util.Log.w("CompanionSync", "Capability probe deferred", it) }
        recipes = RecipeLifecycle(RecipePackageManager(File(filesDir, "recipes"), recipePublicKeys()), store)
        runCatching { recipes.restore() }.onFailure {
            android.util.Log.e("CompanionSync", "Recipe restoration failed", it)
        }
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
        if (outboxJob?.isActive != true) outboxJob = scope.launch { outboxLoop() }
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
                    // B17 §2.3: the heartbeat is the control-plane escape channel —
                    // it carries our cursor + safety barrier out and the server
                    // watermark (+ ≤2 inline events) back. Frozen contract shape:
                    // top-level request/response fields.
                    val control = controlRuntime()
                    control?.let {
                        val fields = it.client.heartbeatRequestFields(
                            it.state.lastAppliedControlSeq(),
                            currentSafetyBarrier(),
                        )
                        payload.put("lastAppliedControlSeq", fields.getLong("lastAppliedControlSeq"))
                        payload.put("safetyBarrier", fields.getString("safetyBarrier"))
                    }
                    android.util.Log.d("CompanionSync", "Sending heartbeat payload: $payload")
                    val heartbeat = withContext(Dispatchers.IO) { client.deviceHeartbeat(payload) }
                    android.util.Log.i("CompanionSync", "Heartbeat successful")
                    runtimeStatus.markPresence(true)
                    retryPolicy.reset()
                    control?.let { runtime ->
                        val watermark = heartbeat.optLong("controlHighWatermark", -1L)
                        val inline = parseInlineControlEvents(heartbeat)
                        if (watermark >= 0 || inline.isNotEmpty()) {
                            runtime.client.onHeartbeatResponse(
                                controlHighWatermark = watermark.coerceAtLeast(0),
                                inlineEvents = inline,
                            )
                        }
                    }
                    ResumeCommand.fromHeartbeat(heartbeat)?.let { pendingResume = it }
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
        val relative = ".automation.CloudCtlAccessibilityService"
        val candidates = setOf(
            "$packageName/$packageName$relative",
            "$packageName/$relative",
        )
        return enabled.split(':').any { it.equals(candidates.first(), ignoreCase = true) || it.equals(candidates.last(), ignoreCase = true) }
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
                // B17 control-plane/v1 §0 (frozen invariant): control-plane
                // synchronization runs FIRST and is never gated by local
                // execution state, queue state, or accessibility readiness —
                // a blocked queue head must not delay cancel delivery. The
                // mirror converges inside the same transactional apply; the
                // SUSPECT_ORPHANED barrier evaluation follows (§3.3: alert +
                // forced sync + snapshot reconcile, never a local unblock);
                // only then do the pre-existing claim gates apply.
                var claimPermittedByControl = true
                val control = controlRuntime()
                if (control != null) {
                    val forceSnapshot = suspectForceSnapshot
                    suspectForceSnapshot = false
                    val pass = runCatching {
                        withContext(Dispatchers.IO) {
                            control.orchestrator.runPreClaimPass(forceSnapshot)
                        }
                    }.onFailure { error ->
                        android.util.Log.w("CompanionSync", "Control sync deferred: ${error.message}")
                    }.getOrNull()
                    if (pass != null) {
                        if (!pass.claimPermitted) claimPermittedByControl = false
                        if (pass.suspect == null) {
                            if (suspectActive) {
                                suspectActive = false
                                runtimeStatus.clearSuspectOrphanedAlert()
                            }
                        } else {
                            suspectActive = true
                        }
                    }
                }
                val resume = pendingResume
                if (resume != null) {
                    pendingResume = null
                    runResume(client, resume)
                    continue
                }
                runCatching { recipes.activatePending() }.onFailure {
                    android.util.Log.e("CompanionSync", "Recipe activation deferred", it)
                }
                if (networkAvailability.isValidated()) {
                    try {
                        val executor = ControlledActionExecutor(store, PinnedControlledActionLedger(configured.first))
                        for (key in executor.reconcilePending()) {
                            val action = store.actionJournal(key) ?: continue
                            runtimeStatus.updateTask(action.taskId,
                                if (action.status == "APPLIED") AuthorizedTaskState.Succeeded else AuthorizedTaskState.Failed,
                                "Server action resolution synchronized", "SERVER_ACTION_RESOLUTION")
                        }
                        withContext(Dispatchers.IO) { syncRecipes(client) }
                    } catch (cancelled: CancellationException) {
                        throw cancelled
                    } catch (error: Exception) {
                        android.util.Log.e("CompanionSync", "Recipe synchronization failed", error)
                    }
                    // B2 churn gate: never claim while the accessibility runtime is
                    // not stably ready — a claimed task would only be released
                    // again. The instant capture leaves the mid-flight disconnect
                    // window to acquireFreshClaimAccessibility's release path.
                    // B17: an active SUSPECT_ORPHANED signal additionally blocks
                    // destructive-task claims until the server resolves it.
                    if (!store.hasBlockingHead() && claimPermittedByControl &&
                        accessibilityRuntimeReadiness().capture() is AccessibilityRuntimeReadiness.Ready<*>
                    ) {
                        claimed = withContext(Dispatchers.IO) { client.claim() }
                    }
                }
                if (claimed != null) {
                    val acceptedDeviceId = try {
                        val command = ClaimedTaskInterpreter.commandOrNull(claimed.taskPayload)
                        if (command != null) {
                            require(command.deviceId == configured.second && claimed.deviceId == configured.second) {
                                "Task belongs to another device"
                            }
                            command.deviceId
                        } else {
                            val task = AutomationTaskParser.parse(claimed.taskPayload)
                            require(task.deviceId == configured.second && claimed.deviceId == configured.second) {
                                "Task belongs to another device"
                            }
                            task.deviceId
                        }
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
                    require(acceptedDeviceId == configured.second)
                    store.enqueueTask(claimed.taskId, claimed.taskPayload, claimed.leaseId, claimed.lastSequence)
                    runtimeStatus.updateTask(
                        claimed.taskId,
                        AuthorizedTaskState.Queued,
                        "已收到云端任务",
                        "TASK_QUEUED",
                    )
                }
                val executed = runNext(client)
                // pa-im/20260913.1: IM push must never block or fail the task loop.
                runCatching { deliverImEvents(client) }
                    .onFailure { android.util.Log.w("CompanionSync", "IM push deferred", it) }
                runCatching { refreshImConfig(client) }
                DutyController.tick(this, store)
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

    private var imConfigFetchedAt = 0L

    private suspend fun refreshImConfig(client: CloudTaskClient) {
        val now = android.os.SystemClock.elapsedRealtime()
        if (now - imConfigFetchedAt < 60_000) return
        imConfigFetchedAt = now
        val raw = client.fetchImConfig() ?: return
        val platforms = buildSet {
            val array = raw.optJSONArray("platforms") ?: return@buildSet
            for (index in 0 until array.length()) add(array.optString(index))
        }.ifEmpty { setOf(com.company.cloudctl.companion.im.ImMonitorConfig.PLATFORM_XIANYU) }
        val config = com.company.cloudctl.companion.im.ImMonitorConfig(
            enabled = raw.optBoolean("enabled", true),
            platforms = platforms,
            mode = raw.optString("mode", com.company.cloudctl.companion.im.ImMonitorConfig.MODE_NOTIFICATION),
            dutyStart = raw.optString("dutyStart", "09:00"),
            dutyEnd = raw.optString("dutyEnd", "23:00"),
        )
        com.company.cloudctl.companion.im.ImMonitor.applyConfig(config)
    }

    private suspend fun deliverImEvents(client: CloudTaskClient) {
        val batch = ImMonitor.drain(20)
        if (batch.isEmpty()) return
        val payload = org.json.JSONObject()
        val messages = org.json.JSONArray()
        batch.forEach { event ->
            messages.put(
                org.json.JSONObject()
                    .put("peerKey", event.peerKey)
                    .put("peerName", event.peerName)
                    .put("text", event.text)
                    .put("occurredAt", event.occurredAt.toString()),
            )
        }
        payload.put("messages", messages)
        try {
            client.sendImMessages(payload)
        } catch (error: Exception) {
            ImMonitor.requeue(batch)
            throw error
        }
    }

    /**
     * im-live slice 2, gap 2: after a xianyu reply task finishes, the conversation
     * page is still open, so the newest inbound bubble can backfill the placeholder
     * body that push notifications deliver (「发来一条新消息」). Best effort only.
     */
    private suspend fun enrichImReplyBody(task: AutomationTask, service: CloudCtlAccessibilityService) {
        val peer = com.company.cloudctl.companion.im.ImReplyTaskShape.peerNameOf(task)
        if (peer == null) {
            android.util.Log.i("CompanionSync", "IM body enrichment: reply task shape not recognized")
            return
        }
        val chatOpen = runCatching {
            service.inspect(
                task.targetPackage,
                com.company.cloudctl.companion.im.ImReplyTaskShape.CHAT_INPUT_LOCATOR,
            )?.visible == true
        }.getOrDefault(false)
        if (!chatOpen) {
            android.util.Log.i("CompanionSync", "IM body enrichment: chat page not open after reply")
            return
        }
        var bubbles = service.chatBubbles(task.targetPackage)
        var attempts = 0
        while (attempts < ENRICH_SWIPE_ATTEMPTS &&
            com.company.cloudctl.companion.im.ChatPageReading.latestInbound(bubbles) == null
        ) {
            attempts++
            // Our own replies push the contact's last message out of the Flutter
            // semantics tree. Drag the list down inside its own bounds (the old
            // fixed start point was consumed by the IME) to reveal it, re-read,
            // and stop as soon as an inbound bubble becomes visible.
            runCatching {
                service.swipeConversationList(task.targetPackage, backward = true)
                delay(ENRICH_SWIPE_SETTLE_MS)
            }
            bubbles = service.chatBubbles(task.targetPackage)
            android.util.Log.i(
                "CompanionSync",
                "IM body enrichment attempt=$attempts bubbles=${bubbles.size} " +
                    "inbound=${com.company.cloudctl.companion.im.ChatPageReading.latestInbound(bubbles) != null}",
            )
        }
        if (attempts > 0) {
            // Restore the view so our newest replies are visible again. Exact
            // placement is not required; bottom overscroll is harmless.
            runCatching {
                repeat(attempts) {
                    service.swipeConversationList(task.targetPackage, backward = false)
                    delay(ENRICH_SWIPE_SETTLE_MS)
                }
            }
        }
        val queued = imBodyEnricher.enrich(peer, bubbles)
        android.util.Log.i(
            "CompanionSync",
            "IM body enrichment peer=${peer.take(32)} bubbles=${bubbles.size} queued=$queued attempts=$attempts",
        )
    }

    private suspend fun runNext(
        client: CloudTaskClient,
    ): Boolean {
        val pending = store.claimNext() ?: return false
        val command = runCatching { ClaimedTaskInterpreter.commandOrNull(pending.payload) }
            .getOrElse {
                failTask(pending.taskId, "TASK_CONTRACT_REJECTED", "任务指令校验未通过")
                return true
            }
        if (command != null) {
            val service = acquireFreshClaimAccessibility(client, pending) ?: return true
            return runCommandV1(client, pending, command, freshService = service)
        }
        val task = runCatching { AutomationTaskParser.parse(pending.payload) }
            .getOrElse {
                failTask(pending.taskId, "TASK_CONTRACT_REJECTED", "任务指令校验未通过")
                return true
            }
        val service = acquireFreshClaimAccessibility(client, pending) ?: return true
        val stall = preflightStallReason(includeAccessibility = false)
        if (stall != null) {
            failTask(task.taskId, stall.first, stall.second, waitingUser = stall.first == "DEVICE_LOCKED")
            return true
        }
        val control = ExecutionControl()
        val commitGate = buildStepsPublishGate(service, task)
        val destructiveGate = buildMaintenanceDestructiveGate(service, task)
        val orderReporter = if (task.steps.any { it is AutomationStep.ReadOrders }) orderReporterFor(client) else null
        val orderScreensReporter = if (task.steps.any { it is AutomationStep.ReadOrders }) {
            orderScreensReporterFor(client, pending, task)
        } else {
            null
        }
        var taskWriteSession: TaskSession? = null
        var releaseBoundary = ReleaseBoundary.COMPLETED
        try {
            // Frozen protocol (R20260916-P09-18): for a fresh claim the initial
            // task heartbeat is the execution boundary. Without a confirmed
            // heartbeat no UI, media, or local execution may start; the task is
            // conservatively start-blocked until the server lease expires and a
            // replacement lease redelivers it.
            val start = FreshClaimExecutionBoundary.run(
                heartbeat = { sendFreshClaimInitialHeartbeat(client, task.taskId, pending.leaseId, control) },
                onHeartbeatFailure = { error ->
                    store.markStartBlocked(task.taskId, heartbeatBlockCode(error))
                },
            ) {
                throwIfControlRequested(control)
                // B10: heartbeat confirmed — the task now holds the device write
                // lease; IM duty / remote / edge writes are rejected until the
                // session returns at a safe boundary.
                taskWriteSession = deviceArbiter.beginTaskSession(task.taskId)
                coroutineScope {
                    val currentStep = AtomicInteger(-1)
                    val heartbeatJob = launch(Dispatchers.IO) {
                        runTaskHeartbeats(client, task.taskId, pending.leaseId, control, currentStep)
                    }
                    try {
                        runtimeStatus.updateTask(task.taskId, AuthorizedTaskState.Running, "正在准备素材与目标应用", "TASK_PREFLIGHT")
                        prepareMedia(task.taskId, pending.payload)
                        throwIfControlRequested(control)
                        android.util.Log.i(
                            "CompanionSync",
                            "preflight launch targetPackage=${task.targetPackage} " +
                                "xianyu=com.taobao.idlefish",
                        )
                        service.launchTargetApp(
                            task.targetPackage,
                            writer = UiWriter.TASK,
                            fencingToken = taskWriteSession?.fencingToken,
                        )
                        throwIfControlRequested(control)
                        runtimeStatus.updateTask(
                            task.taskId,
                            AuthorizedTaskState.Running,
                            "正在启动本地执行器",
                            "TASK_STARTED",
                        )
                        withTimeout(task.maxRunSeconds * 1_000L) {
                            service.execute(
                                task, control, startAfterIndex = -1, commitGate = commitGate,
                                destructiveGate = destructiveGate, orderReporter = orderReporter,
                                orderScreensReporter = orderScreensReporter,
                            ) { step, state ->
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
                        // im-live slice 2, gap 2: backfill the placeholder notification body
                        // with the real conversation text; never blocks or fails the task.
                        runCatching { enrichImReplyBody(task, service) }
                            .onFailure { android.util.Log.w("CompanionSync", "IM body enrichment skipped", it) }
                    } finally {
                        heartbeatJob.cancelAndJoin()
                    }
                }
                if (store.unresolvedControlledActionKeys().any { store.actionJournal(it)?.taskId == task.taskId }) {
                    showReconciling(task.taskId)
                } else {
                    store.finish(task.taskId, true)
                    runtimeStatus.updateTask(
                        task.taskId,
                        AuthorizedTaskState.Succeeded,
                        "本地任务已完成",
                        "TASK_SUCCEEDED",
                    )
                }
            }
            if (start is FreshClaimStart.Blocked) {
                android.util.Log.w("CompanionSync", "fresh claim start blocked task=${task.taskId}")
                runtimeStatus.updateTask(
                    task.taskId,
                    AuthorizedTaskState.WaitingConfirmation,
                    "初始心跳未确认，本地保持阻断，等待服务端租约回收",
                    "TASK_START_BLOCKED",
                )
                return true
            }
        } catch (paused: TaskPausedException) {
            releaseBoundary = ReleaseBoundary.PAUSED_CHECKPOINT
            persistPaused(task.taskId, pending, paused)
        } catch (cancelled: CancellationException) {
            releaseBoundary = ReleaseBoundary.CANCELLED
            store.finish(task.taskId, false, "CANCELLED")
            runtimeStatus.updateTask(
                task.taskId,
                AuthorizedTaskState.Canceled,
                "任务已取消",
                "CANCELLED",
            )
            throw cancelled
        } catch (failure: ExecutorFailure) {
            if (control.pauseRequested) {
                releaseBoundary = ReleaseBoundary.PAUSED_CHECKPOINT
                persistPaused(task.taskId, pending, TaskPausedException(null, -1, control.reason))
                return true
            }
            releaseBoundary = ReleaseBoundary.FAILED
            val waiting = failure.code in setOf("UNKNOWN_PAGE", "LAUNCH_REQUIRES_USER", "DEVICE_LOCKED")
            failTask(task.taskId, failure.code, failure.message ?: failure.code, waitingUser = waiting)
        } catch (error: Exception) {
            if (control.pauseRequested) {
                releaseBoundary = ReleaseBoundary.PAUSED_CHECKPOINT
                persistPaused(task.taskId, pending, TaskPausedException(null, -1, control.reason))
                return true
            }
            releaseBoundary = ReleaseBoundary.FAILED
            failTask(task.taskId, "TASK_EXECUTION_FAILED", error.message ?: "本地任务已安全终止")
        } finally {
            // B10: hand the device back at the classified safe boundary. A late
            // or duplicate release (stale token) is a no-op inside the arbiter.
            taskWriteSession?.let {
                deviceArbiter.endTaskSession(it.fencingToken, releaseBoundary)
            }
        }
        return true
    }

    private suspend fun runResume(client: CloudTaskClient, command: ResumeCommand) {
        if (!store.markResumeCheck(command.taskId, command.leaseId)) return
        val pending = store.claimResume(command.taskId) ?: return
        val claimedCommand = runCatching { ClaimedTaskInterpreter.commandOrNull(pending.payload) }
            .getOrElse {
                failTask(pending.taskId, "TASK_CONTRACT_REJECTED", "任务指令校验未通过")
                return
            }
        if (claimedCommand != null) {
            runCommandV1(client, pending, claimedCommand, resume = command)
            return
        }
        val task = runCatching { AutomationTaskParser.parse(pending.payload) }
            .getOrElse {
                failTask(pending.taskId, "TASK_CONTRACT_REJECTED", "任务指令校验未通过")
                return
            }
        val stall = preflightStallReason()
        if (stall != null) {
            failTask(task.taskId, stall.first, stall.second, waitingUser = stall.first == "DEVICE_LOCKED")
            return
        }
        val service = awaitAccessibilityService(task.taskId) ?: return
        val commitGate = buildStepsPublishGate(service, task)
        val destructiveGate = buildMaintenanceDestructiveGate(service, task)
        val orderReporter = if (task.steps.any { it is AutomationStep.ReadOrders }) orderReporterFor(client) else null
        val orderScreensReporter = if (task.steps.any { it is AutomationStep.ReadOrders }) {
            orderScreensReporterFor(client, pending, task)
        } else {
            null
        }
        val checkpoint = store.latestCheckpoint(task.taskId)
        if (checkpoint == null) {
            persistPaused(task.taskId, pending, TaskPausedException(null, -1, "resume checkpoint missing"))
            return
        }
        val control = ExecutionControl()
        val startAfterIndex = checkpoint.optInt("loopCursor", -1)
        var taskWriteSession: TaskSession? = null
        var releaseBoundary = ReleaseBoundary.COMPLETED
        try {
            // B10: the resume claim owns the device write lease from its first
            // launch through the classified safe boundary in the finally below.
            taskWriteSession = deviceArbiter.beginTaskSession(task.taskId)
            service.launchTargetApp(
                task.targetPackage,
                writer = UiWriter.TASK,
                fencingToken = taskWriteSession.fencingToken,
            )
            ResumeValidator.guard(
                service,
                task,
                checkpoint,
                JSONObject(pending.payload),
                command.pageVerified,
            )
            sendInitialHeartbeat(client, task.taskId, pending.leaseId, control)
            throwIfControlRequested(control)
            coroutineScope {
                val currentStep = AtomicInteger(startAfterIndex)
                val heartbeatJob = launch(Dispatchers.IO) {
                    runTaskHeartbeats(client, task.taskId, pending.leaseId, control, currentStep)
                }
                try {
                    runtimeStatus.updateTask(
                        task.taskId,
                        AuthorizedTaskState.Running,
                        "正在从检查点继续原任务",
                        "RESUME_CHECK",
                    )
                    withTimeout(task.maxRunSeconds * 1_000L) {
                        service.execute(
                            task, control, startAfterIndex, commitGate = commitGate,
                            destructiveGate = destructiveGate, orderReporter = orderReporter,
                            orderScreensReporter = orderScreensReporter,
                        ) { step, state ->
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
                    // im-live slice 2, gap 2: enrichment also covers resumed reply tasks.
                    runCatching { enrichImReplyBody(task, service) }
                        .onFailure { android.util.Log.w("CompanionSync", "IM body enrichment skipped", it) }
                } finally {
                    heartbeatJob.cancelAndJoin()
                }
            }
            if (store.unresolvedControlledActionKeys().any { store.actionJournal(it)?.taskId == task.taskId }) {
                showReconciling(task.taskId)
            } else {
                store.finish(task.taskId, true)
                runtimeStatus.updateTask(
                    task.taskId,
                    AuthorizedTaskState.Succeeded,
                    "本地任务已完成",
                    "TASK_SUCCEEDED",
                )
            }
        } catch (paused: TaskPausedException) {
            releaseBoundary = ReleaseBoundary.PAUSED_CHECKPOINT
            persistPaused(task.taskId, pending, paused)
        } catch (cancelled: CancellationException) {
            releaseBoundary = ReleaseBoundary.CANCELLED
            store.finish(task.taskId, false, "CANCELLED")
            runtimeStatus.updateTask(task.taskId, AuthorizedTaskState.Canceled, "任务已取消", "CANCELLED")
            throw cancelled
        } catch (failure: ExecutorFailure) {
            releaseBoundary = ReleaseBoundary.FAILED
            if (failure.code in setOf(
                    "RESUME_PAGE_MISMATCH",
                    "RESUME_PAGE_UNVERIFIED",
                    "RESUME_ACCOUNT_CHANGED",
                    "RESUME_BINDING_CHANGED",
                    "RESUME_RECIPE_INCOMPATIBLE",
                    "WRONG_ACTIVE_PACKAGE",
                    "ACTIVE_WINDOW_MISSING",
                    "APP_NOT_FOREGROUND",
                    "ACCESSIBILITY_NOT_ACTIVE",
                )
            ) {
                releaseBoundary = ReleaseBoundary.PAUSED_CHECKPOINT
                persistPaused(
                    task.taskId,
                    pending,
                    TaskPausedException(checkpoint.optString("itemId").ifBlank { null }, startAfterIndex, failure.message),
                )
                return
            }
            if (control.pauseRequested) {
                releaseBoundary = ReleaseBoundary.PAUSED_CHECKPOINT
                persistPaused(task.taskId, pending, TaskPausedException(null, -1, control.reason))
                return
            }
            failTask(task.taskId, failure.code, failure.message ?: failure.code)
        } catch (error: Exception) {
            if (control.pauseRequested) {
                releaseBoundary = ReleaseBoundary.PAUSED_CHECKPOINT
                persistPaused(task.taskId, pending, TaskPausedException(null, -1, control.reason))
                return
            }
            releaseBoundary = ReleaseBoundary.FAILED
            failTask(task.taskId, "TASK_EXECUTION_FAILED", error.message ?: "本地任务已安全终止")
        } finally {
            taskWriteSession?.let {
                deviceArbiter.endTaskSession(it.fencingToken, releaseBoundary)
            }
        }
    }

    private fun syncRecipes(client: CloudTaskClient) {
        recipes.synchronize(client.listActiveRecipes().toString()) { versionId -> downloadRecipe(client, versionId) }
    }

    private fun downloadRecipe(client: CloudTaskClient, versionId: String): RecipeDownload {
        val downloaded = client.downloadRecipe(versionId)
        return RecipeDownload(downloaded.body.toString(Charsets.UTF_8), downloaded.headers["x-content-sha256"])
    }

    private fun recipePublicKeys(): Map<String, String> {
        val encoded = BuildConfig.RECIPE_SIGNING_PUBLIC_KEYS
        if (encoded.isBlank() || encoded == "{}") return emptyMap()
        val root = JSONObject(encoded)
        val keys = mutableMapOf<String, String>()
        root.keys().forEach { key -> keys[key] = root.getString(key) }
        return keys
    }

    private suspend fun runCommandV1(
        client: CloudTaskClient,
        pending: PendingTask,
        command: CommandV1,
        resume: ResumeCommand? = null,
        freshService: CloudCtlAccessibilityService? = null,
    ): Boolean {
        // Fresh commands already hold a verified accessibility runtime from the
        // caller; only resume paths re-check it here.
        val stall = preflightStallReason(includeAccessibility = freshService == null)
        if (stall != null) {
            failTask(command.taskId, stall.first, stall.second, waitingUser = stall.first == "DEVICE_LOCKED")
            return true
        }
        val service = freshService ?: awaitAccessibilityService(command.taskId) ?: return true
        val control = ExecutionControl()
        val checkpoint = store.latestCheckpoint(command.taskId)
        var recipeProgress: RecipeResumeProgress? = null
        var parsedRecipe: RecipePackage? = null
        var taskWriteSession: TaskSession? = null
        var releaseBoundary = ReleaseBoundary.COMPLETED
        try {
            val recipeJson = withContext(Dispatchers.IO) {
                recipes.ensureCommand(command) { versionId -> downloadRecipe(client, versionId) }
            }
            val engine = RecipeEngine(service, elapsedMs = { android.os.SystemClock.elapsedRealtime() })
            val recipe = engine.parse(recipeJson, expectedHash = command.recipeSha256)
            parsedRecipe = recipe
            val configured = loadConnection()
                ?: throw ExecutorFailure("CLOUD_UNAVAILABLE", "Cloud connection unavailable")
            val commitAdapter = RecipeCommitAdapter(
                ControlledActionExecutor(store, PinnedControlledActionLedger(configured.first)), service,
            )
            val progress = if (resume == null) {
                RecipeResumeProgress.fresh(recipe)
            } else {
                val resumeCheckpoint = checkpoint
                if (resumeCheckpoint == null) {
                    persistResumeRejected(command.taskId, null, "resume checkpoint missing")
                    return true
                }
                RecipeResumeProgress.resume(recipe, command, resumeCheckpoint)
            }
            recipeProgress = progress
            if (resume != null) {
                val resumeFromStateId = requireNotNull(progress.nextStateId)
                ResumeValidator.guard(
                    service,
                    AutomationTask(
                        taskId = command.taskId,
                        deviceId = command.deviceId,
                        targetPackage = command.targetPackage,
                        issuedAt = java.time.Instant.now(),
                        expiresAt = java.time.Instant.now().plusSeconds(recipe.maxDurationMs / 1000 + 1),
                        maxRunSeconds = (recipe.maxDurationMs / 1000).toInt().coerceIn(1, 900),
                        steps = emptyList(),
                    ),
                    requireNotNull(checkpoint),
                    JSONObject(pending.payload),
                    resume.pageVerified,
                    recipe,
                    resumeFromStateId,
                )
            }
            if (resume == null) {
                // Fresh claims share the strict heartbeat boundary: no recipe
                // execution may start until the server confirms the lease.
                try {
                    sendFreshClaimInitialHeartbeat(client, command.taskId, pending.leaseId, control)
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (failure: Exception) {
                    store.markStartBlocked(command.taskId, heartbeatBlockCode(failure))
                    android.util.Log.w("CompanionSync", "fresh command start blocked task=${command.taskId}")
                    runtimeStatus.updateTask(
                        command.taskId,
                        AuthorizedTaskState.WaitingConfirmation,
                        "初始心跳未确认，本地保持阻断，等待服务端租约回收",
                        "TASK_START_BLOCKED",
                    )
                    return true
                }
            } else {
                sendInitialHeartbeat(client, command.taskId, pending.leaseId, control)
            }
            throwIfControlRequested(control)
            // B10: heartbeat confirmed — the recipe command holds the device
            // write lease until the classified safe boundary in the finally.
            taskWriteSession = deviceArbiter.beginTaskSession(command.taskId)
            coroutineScope {
                val currentStep = AtomicInteger(
                    progress.lastSuccessfulStateId?.let { recipe.states.keys.indexOf(it) } ?: -1,
                )
                val heartbeatJob = launch(Dispatchers.IO) {
                    runTaskHeartbeats(client, command.taskId, pending.leaseId, control, currentStep)
                }
                try {
                    runtimeStatus.updateTask(
                        command.taskId,
                        AuthorizedTaskState.Running,
                        if (resume != null) "正在从检查点继续原任务" else "正在执行 CommandV1",
                        if (resume != null) "RESUME_CHECK" else "TASK_STARTED",
                    )
                    prepareMedia(command.taskId, pending.payload)
                    throwIfControlRequested(control)
                    service.launchTargetApp(
                        command.targetPackage,
                        writer = UiWriter.TASK,
                        fencingToken = taskWriteSession?.fencingToken,
                    )
                    throwIfControlRequested(control)
                    val resumeFromStateId = progress.nextStateId.takeIf { resume != null }
                    val outcome = withTimeout(recipe.maxDurationMs) {
                        engine.execute(
                            recipe,
                            command,
                            resumeFromStateId = resumeFromStateId,
                            controlCheckpoint = { throwIfControlRequested(control) },
                            commitAction = { state ->
                                commitAdapter.execute(command, state) {
                                    throwIfControlRequested(control)
                                }
                            },
                        ) { stateId, state ->
                            val eventType = progress.record(recipe, stateId, state)
                            currentStep.set(progress.lastSuccessfulStateId?.let { recipe.states.keys.indexOf(it) } ?: -1)
                            if (eventType == "PAUSED_WAITING_USER") {
                                store.record(command.taskId, stateId, state, eventType)
                            } else {
                                store.recordStepEvent(
                                    taskId = command.taskId,
                                    stepId = stateId,
                                    state = state,
                                    detailCode = "STEP_$state",
                                    eventType = eventType,
                                    stepIndex = null,
                                    payload = JSONObject().put("detailCode", "STEP_$state"),
                                )
                            }
                            runtimeStatus.updateTask(
                                command.taskId,
                                AuthorizedTaskState.Running,
                                "$stateId: $state",
                                "STEP_$state",
                                stateId,
                            )
                            if (progress.nextStateId != null) throwIfControlRequested(control)
                        }
                    }
                    when {
                        outcome == "RECONCILING" -> showReconciling(command.taskId)
                        outcome == "WAITING_USER" -> {
                            persistRecipePaused(command, recipe, progress, "OPEN_ONLY waiting for operator")
                        }
                        outcome == "SUCCEEDED" && ClaimedTaskInterpreter.isOpenOnly(command) -> {
                            failTask(
                                command.taskId,
                                "OPEN_ONLY_NOT_COMMITTED",
                                "OPEN_ONLY recipe is not an execution success",
                                waitingUser = true,
                            )
                        }
                        outcome == "SUCCEEDED" -> {
                            store.finish(command.taskId, true)
                            runtimeStatus.updateTask(
                                command.taskId,
                                AuthorizedTaskState.Succeeded,
                                "本地任务已完成",
                                "TASK_SUCCEEDED",
                            )
                        }
                        else -> failTask(command.taskId, "TASK_FAILED", outcome)
                    }
                } finally {
                    heartbeatJob.cancelAndJoin()
                }
            }
        } catch (paused: TaskPausedException) {
            releaseBoundary = ReleaseBoundary.PAUSED_CHECKPOINT
            val progress = recipeProgress
            val recipe = parsedRecipe
            if (progress?.nextStateId != null && recipe != null) {
                persistRecipePaused(command, recipe, progress, paused.message)
            } else {
                persistPaused(command.taskId, pending, paused)
            }
        } catch (cancelled: CancellationException) {
            releaseBoundary = ReleaseBoundary.CANCELLED
            store.finish(command.taskId, false, "CANCELLED")
            runtimeStatus.updateTask(command.taskId, AuthorizedTaskState.Canceled, "任务已取消", "CANCELLED")
            throw cancelled
        } catch (failure: ExecutorFailure) {
            releaseBoundary = ReleaseBoundary.FAILED
            if (resume != null && (
                    failure.code.startsWith("RESUME_") || failure.code in setOf(
                    "WRONG_ACTIVE_PACKAGE",
                    "ACTIVE_WINDOW_MISSING",
                    "APP_NOT_FOREGROUND",
                    "ACCESSIBILITY_NOT_ACTIVE",
                    )
                )
            ) {
                releaseBoundary = ReleaseBoundary.PAUSED_CHECKPOINT
                persistResumeRejected(command.taskId, checkpoint, failure.message)
                return true
            }
            if (control.cancelRequested) {
                releaseBoundary = ReleaseBoundary.CANCELLED
                store.finish(command.taskId, false, "CANCELLED")
                runtimeStatus.updateTask(command.taskId, AuthorizedTaskState.Canceled, "任务已取消", "CANCELLED")
                return true
            }
            if (control.pauseRequested) {
                releaseBoundary = ReleaseBoundary.PAUSED_CHECKPOINT
                val progress = recipeProgress
                val recipe = parsedRecipe
                if (progress?.nextStateId != null && recipe != null) {
                    persistRecipePaused(command, recipe, progress, control.reason)
                } else {
                    persistPaused(command.taskId, pending, TaskPausedException(null, -1, control.reason))
                }
                return true
            }
            failTask(command.taskId, failure.code, failure.message ?: failure.code)
        } catch (error: Exception) {
            if (control.pauseRequested) {
                releaseBoundary = ReleaseBoundary.PAUSED_CHECKPOINT
                persistPaused(command.taskId, pending, TaskPausedException(null, -1, control.reason))
                return true
            }
            releaseBoundary = ReleaseBoundary.FAILED
            failTask(command.taskId, "TASK_EXECUTION_FAILED", error.message ?: "本地任务已安全终止")
        } finally {
            taskWriteSession?.let {
                deviceArbiter.endTaskSession(it.fencingToken, releaseBoundary)
            }
            if (store.unresolvedControlledActionKeys().any { store.actionJournal(it)?.taskId == command.taskId }) {
                showReconciling(command.taskId)
            }
        }
        return true
    }

    private fun buildStepsPublishGate(
        service: CloudCtlAccessibilityService,
        task: AutomationTask,
    ): CommitGate? {
        if (task.targetPackage !in setOf(
                TargetLocatorRegistry.XIANYU_PACKAGE,
                TargetLocatorRegistry.XHS_PACKAGE,
                TargetLocatorRegistry.DOUYIN_PACKAGE,
            )
        ) return null
        val publishes = task.steps.any {
            it is AutomationStep.Tap &&
                it.locatorRef in setOf("xianyu_publish_button", "xhs_publish_button", "dy_publish_button")
        }
        if (!publishes) return null
        val connection = loadConnection()?.first ?: return null
        return StepsPublishCommitGate(
            ControlledActionExecutor(store, PinnedControlledActionLedger(connection)),
            service,
        )
    }

    /**
     * Gated destructive confirms for the xianyu maintenance steps task
     * (contract xianyu-maintenance-anchors-20260915): delist/delete confirm
     * strikes run through the controlled ledger. Only built when the task
     * actually carries such a strike; otherwise the executor fails closed on
     * G3_NOT_ACCEPTED, and a task without a controlled connection fails the
     * same way instead of ever tapping ungated.
     */
    private fun buildMaintenanceDestructiveGate(
        service: CloudCtlAccessibilityService,
        task: AutomationTask,
    ): DestructiveClickGate? {
        if (task.targetPackage != TargetLocatorRegistry.XIANYU_PACKAGE) return null
        val confirms = hasMaintenanceDestructiveConfirm(task)
        if (!confirms) return null
        val connection = loadConnection()?.first ?: return null
        return XianyuMaintenanceCommitGate(
            ControlledActionExecutor(store, PinnedControlledActionLedger(connection)),
            service,
        )
    }

    /**
     * order-sync/20260915.1 §5: the moment a readOrders step succeeds, its
     * collected rows go straight to the §3 batch endpoint (maxRows ≤ 10 fits
     * the 1..20 batch limit in one shot). Best-effort by design: the task
     * result itself keeps flowing through the ordinary completion events, an
     * upload failure only logs (slice 1 has no orders outbox; re-collection
     * is idempotent server-side). An empty read reports 0 rows here — the
     * batch endpoint requires 1..20 rows, so nothing is POSTed for it.
     *
     * Slice 2 (order-sync-slice2/20260915.1 §3): one call per screen, so a
     * later screen failing never loses the screens already uploaded. The
     * screen ordinal is log material only (screen=N) — it never enters the
     * §3 batch payload.
     */
    private fun orderReporterFor(client: CloudTaskClient): OrderReporter = OrderReporter { taskId, direction, collected, skipped, screen ->
        if (collected.isEmpty()) {
            android.util.Log.i(
                "CompanionSync",
                "orders batch task=$taskId direction=$direction screen=$screen " +
                    "rows=0 skipped=${skipped.size} (nothing uploaded)",
            )
            return@OrderReporter
        }
        try {
            val payload = buildOrdersBatchPayload(collected, java.time.Instant.now())
            val response = withContext(Dispatchers.IO) { client.sendOrders(payload) }
            val result = parseOrdersBatchResponse(response)
            android.util.Log.i(
                "CompanionSync",
                "orders batch task=$taskId direction=$direction screen=$screen " +
                    "accepted=${result.accepted} duplicates=${result.duplicates} skipped=${skipped.size}",
            )
        } catch (cancelled: kotlinx.coroutines.CancellationException) {
            throw cancelled
        } catch (rejected: CloudHttpException) {
            // §3: 422 carries per-row rejection detail — keep it in the log for
            // diagnosis instead of the bare status line.
            android.util.Log.w(
                "CompanionSync",
                "orders batch upload rejected task=$taskId screen=$screen status=${rejected.status} " +
                    "body=${rejected.responseBody.take(500)}",
            )
        } catch (error: Exception) {
            android.util.Log.w("CompanionSync", "orders batch upload deferred task=$taskId: ${error.message}")
        }
    }

    /**
     * O10 dual-write (fleet-first-20260916.1): per-screen page payload for
     * POST /companion/v2/orders/screens. runKey = the claim's task id (an
     * offline replay of the same screen stays idempotent server-side);
     * accountKey = the claimed payload's accountId, degrading to device
     * attribution when the claim carries no account; schemaVersion frozen at
     * [ORDER_SCREENS_SCHEMA_VERSION]. After a successful push the
     * OrderCheckpoint advances (account/schema/device/direction-bound via
     * bindsTo) and persists in the lightweight orders-checkpoint prefs — the
     * same SharedPreferences mechanism the binding store already uses; a
     * decode failure or refused binding starts fresh from screen 1
     * (fail-closed, never a guessed position). Push failures mirror the
     * slice1 batch channel: logged, never task-fatal.
     */
    private fun orderScreensReporterFor(
        client: CloudTaskClient,
        pending: PendingTask,
        task: AutomationTask,
    ): OrderScreensReporter {
        val accountKey = runCatching {
            JSONObject(pending.payload).optString("accountId").takeIf { it.isNotBlank() }
        }.getOrNull() ?: task.deviceId
        return OrderScreensReporter { taskId, direction, page, summary, rows, partialRowIndices ->
            try {
                val payload = buildOrdersScreenPayload(
                    runKey = taskId,
                    accountKey = accountKey,
                    schemaVersion = ORDER_SCREENS_SCHEMA_VERSION,
                    direction = direction,
                    screen = page.screen,
                    rows = rows,
                    partialRowIndices = partialRowIndices,
                    collectedAt = summary.collectedAt,
                )
                val response = withContext(Dispatchers.IO) { client.sendOrdersScreen(payload) }
                advanceAndPersistOrderCheckpoint(task, direction, page, accountKey)
                android.util.Log.i(
                    "CompanionSync",
                    "orders screen task=$taskId direction=$direction screen=${page.screen} " +
                        "accepted=${response.optInt("accepted", -1)} updated=${response.optInt("updated", -1)} " +
                        "duplicates=${response.optInt("duplicates", -1)} replayed=${response.optBoolean("replayed", false)}",
                )
            } catch (cancelled: kotlinx.coroutines.CancellationException) {
                throw cancelled
            } catch (rejected: CloudHttpException) {
                // 409 carries the checkpoint binding verdict (account/version/
                // run/screen-gap) — keep the body for diagnosis.
                android.util.Log.w(
                    "CompanionSync",
                    "orders screen push rejected task=$taskId screen=${page.screen} " +
                        "status=${rejected.status} body=${rejected.responseBody.take(500)}",
                )
            } catch (error: Exception) {
                android.util.Log.w(
                    "CompanionSync",
                    "orders screen push deferred task=$taskId screen=${page.screen}: ${error.message}",
                )
            }
        }
    }

    /** O10 checkpoint feed: advance the direction-bound checkpoint after a successful screen push. */
    private fun advanceAndPersistOrderCheckpoint(
        task: AutomationTask,
        direction: OrderDirection,
        page: OrderPageReading,
        accountKey: String,
    ) {
        runCatching {
            val prefs = getSharedPreferences("cloudctl_orders_checkpoint", MODE_PRIVATE)
            val prior = prefs.getString(direction.name, null)?.let { OrderCheckpoint.decode(it) }
            // Only a checkpoint that binds to THIS account/schema/device/
            // direction/run may resume; anything else (new run, switched
            // account, version bump) restarts from this run's own screen 1.
            val resumable = prior?.takeIf {
                it.bindsTo(
                    accountKey, ORDER_SCREENS_SCHEMA_VERSION, task.deviceId, direction, task.taskId,
                ) is OrderCheckpoint.BindResult.Resume
            }
            val base = resumable ?: OrderCheckpoint(
                accountKey = accountKey,
                schemaVersion = ORDER_SCREENS_SCHEMA_VERSION,
                deviceKey = task.deviceId,
                direction = direction,
                runKey = task.taskId,
                lastScreen = 0,
                seenKeyCount = 0,
            )
            val advanced = base.advance(page.screen, page.newKeyCount)
            prefs.edit().putString(direction.name, advanced.encode()).apply()
            android.util.Log.i(
                "CompanionSync",
                "orders checkpoint direction=$direction run=${task.taskId.take(16)} " +
                    "lastScreen=${advanced.lastScreen} seenKeys=${advanced.seenKeyCount}",
            )
        }.onFailure {
            android.util.Log.w("CompanionSync", "orders checkpoint persist deferred: ${it.message}")
        }
    }

    private fun showReconciling(taskId: String) {
        runtimeStatus.updateTask(taskId, AuthorizedTaskState.WaitingConfirmation,
            "提交结果等待云端核对，不会重新执行", "RECONCILING")
    }

    private fun persistRecipePaused(
        command: CommandV1,
        recipe: RecipePackage,
        progress: RecipeResumeProgress,
        reason: String?,
    ) {
        val checkpoint = progress.checkpoint(recipe)
        store.saveCheckpoint(
            command.taskId,
            command.attemptId,
            checkpoint.nextStateId,
            command.snapshotSha256,
            command.recipeSha256,
            command.accountId,
            command.bindingVersion,
            checkpoint.lastSuccessfulStateIndex,
            checkpoint.lastSuccessfulStateId,
        )
        store.markPaused(
            command.taskId,
            checkpoint.lastSuccessfulStateId,
            checkpoint.lastSuccessfulStateIndex,
            reason,
        )
        runtimeStatus.updateTask(
            command.taskId,
            AuthorizedTaskState.WaitingConfirmation,
            "已在安全点暂停，等待人工接管",
            "PAUSED_WAITING_USER",
            checkpoint.nextStateId,
        )
    }

    private fun persistResumeRejected(
        taskId: String,
        checkpoint: JSONObject?,
        reason: String?,
    ) {
        val lastSuccessfulStateId = checkpoint?.optString("itemId")?.takeIf { it.isNotBlank() }
        val lastSuccessfulStateIndex = checkpoint?.optInt("loopCursor", -1) ?: -1
        store.markPaused(taskId, lastSuccessfulStateId, lastSuccessfulStateIndex, reason)
        runtimeStatus.updateTask(
            taskId,
            AuthorizedTaskState.WaitingConfirmation,
            "恢复检查未通过，任务保持暂停",
            "PAUSED_WAITING_USER",
            checkpoint?.optString("stateId")?.takeIf { it.isNotBlank() },
        )
    }

    private suspend fun prepareMedia(taskId: String, payload: String) {
        val media = runCatching { JSONObject(payload).optJSONObject("mediaDelivery") }.getOrNull() ?: return
        val deliveryId = media.optString("deliveryId")
        val values = media.optJSONArray("assetIds")
        if (deliveryId.isBlank() || values == null || values.length() !in 1..50) {
            throw ExecutorFailure("MEDIA_DELIVERY_CONTRACT_REJECTED", "media delivery contract rejected")
        }
        val assetIds = List(values.length()) { index -> values.getString(index) }
        if (assetIds.any { !it.matches(Regex("^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")) }) {
            throw ExecutorFailure("MEDIA_DELIVERY_CONTRACT_REJECTED", "media delivery contract rejected")
        }
        val configured = loadConnection() ?: throw ExecutorFailure("CLOUD_UNAVAILABLE", "Cloud connection unavailable")
        runtimeStatus.updateTask(taskId, AuthorizedTaskState.Running, "正在下载任务素材", "MEDIA_DOWNLOAD_STARTED")
        try {
            withContext(Dispatchers.IO) {
                mediaDeliveryCoordinator.deliver(configured.first, deliveryId, assetIds)
            }
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Exception) {
            throw ExecutorFailure("MEDIA_DOWNLOAD_FAILED", error.message ?: "media download failed")
        }
        runtimeStatus.updateTask(taskId, AuthorizedTaskState.Running, "任务素材已校验", "MEDIA_DOWNLOAD_SUCCEEDED")
    }

    private fun accessibilityRuntimeReadiness() = AccessibilityRuntimeReadinessWaiter(
        timeoutMillis = ACCESSIBILITY_RUNTIME_WAIT_MILLIS,
        pollIntervalMillis = ACCESSIBILITY_RUNTIME_POLL_MILLIS,
        isEnabled = ::accessibilityEnabled,
        activeService = { CloudCtlAccessibilityService.active },
        sleep = { delay(it) },
    )

    private suspend fun awaitAccessibilityService(taskId: String): CloudCtlAccessibilityService? {
        val readiness = accessibilityRuntimeReadiness().await()
        return when (readiness) {
            is AccessibilityRuntimeReadiness.Ready -> readiness.service
            AccessibilityRuntimeReadiness.NotEnabled -> {
                failTask(taskId, "ACCESSIBILITY_NOT_ENABLED", "无障碍服务未启用")
                null
            }
            AccessibilityRuntimeReadiness.NotActive -> {
                failTask(taskId, "ACCESSIBILITY_NOT_ACTIVE", "无障碍服务已启用但尚未激活")
                null
            }
        }
    }

    /**
     * Frozen protocol (R20260916-P09-18): a fresh local claim that cannot reach
     * a stable accessibility runtime must release the server task back to the
     * queue BEFORE any heartbeat, media, or UI work. Only a successful server
     * release settles the local copy; a failed release leaves the task
     * conservatively blocked — never re-executed, never locally requeued, and
     * never uploaded as /fail.
     */
    private suspend fun acquireFreshClaimAccessibility(
        client: CloudTaskClient,
        pending: PendingTask,
    ): CloudCtlAccessibilityService? {
        val coordinator = FreshClaimExecutionCoordinator(
            awaitAccessibility = { accessibilityRuntimeReadiness().await() },
            markReleaseBlocked = { reason -> store.markReleaseBlocked(pending.taskId, reason) },
            release = { reason ->
                withContext(Dispatchers.IO) { client.release(pending.taskId, pending.leaseId, reason) }
            },
            settleReleased = { reason -> store.settleReleased(pending.taskId, reason) },
        )
        return when (val outcome = coordinator.acquire()) {
            is FreshClaimAccessibility.Ready -> outcome.service
            is FreshClaimAccessibility.Released -> {
                android.util.Log.i(
                    "CompanionSync",
                    "fresh claim released task=${pending.taskId} reason=${outcome.reason}",
                )
                runtimeStatus.updateTask(
                    pending.taskId,
                    AuthorizedTaskState.WaitingConfirmation,
                    "无障碍不可用，任务已安全释放回云端队列",
                    "TASK_RELEASED",
                )
                null
            }
            is FreshClaimAccessibility.ReleaseBlocked -> {
                android.util.Log.e(
                    "CompanionSync",
                    "fresh claim release blocked task=${pending.taskId} reason=${outcome.reason}",
                    outcome.error,
                )
                runtimeStatus.updateTask(
                    pending.taskId,
                    AuthorizedTaskState.WaitingConfirmation,
                    "无障碍不可用且释放失败，本地阻断等待服务端租约回收",
                    "TASK_RELEASE_BLOCKED",
                )
                null
            }
        }
    }

    /** Strict initial heartbeat for fresh claims: retry transient failures, then fail closed. */
    private suspend fun sendFreshClaimInitialHeartbeat(
        client: CloudTaskClient,
        taskId: String,
        leaseId: String,
        control: ExecutionControl,
    ) {
        var lastError: Exception? = null
        var backoffMs = HEARTBEAT_RETRY_INITIAL_MILLIS
        repeat(FRESH_HEARTBEAT_ATTEMPTS) { attempt ->
            try {
                val heartbeat = withContext(Dispatchers.IO) { client.heartbeat(taskId, leaseId, null) }
                applyHeartbeatControl(control, heartbeat)
                return
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: CloudHttpException) {
                if (error.status == 409) {
                    throw ExecutorFailure("LEASE_FENCED", "stale lease or control epoch rejected")
                }
                if (!error.retryable) throw error
                lastError = error
            } catch (error: java.io.IOException) {
                lastError = error
            }
            if (attempt < FRESH_HEARTBEAT_ATTEMPTS - 1) {
                delay(backoffMs)
                backoffMs = (backoffMs * 2).coerceAtMost(HEARTBEAT_RETRY_MAXIMUM_MILLIS)
            }
        }
        throw ExecutorFailure(
            "HEARTBEAT_UNCONFIRMED",
            "initial task heartbeat could not be confirmed: ${lastError?.message ?: "unknown"}",
        )
    }

    private fun heartbeatBlockCode(error: Exception): String =
        (error as? ExecutorFailure)?.code ?: "HEARTBEAT_UNCONFIRMED"

    private fun preflightStallReason(includeAccessibility: Boolean = true): Pair<String, String>? {
        if (includeAccessibility && !accessibilityEnabled()) return "ACCESSIBILITY_NOT_ENABLED" to "无障碍服务未启用"
        val keyguard = getSystemService(KeyguardManager::class.java)
        if (keyguard?.isKeyguardLocked == true) return "DEVICE_LOCKED" to "设备已锁屏，等待人工解锁"
        val stat = runCatching { StatFs(filesDir.absolutePath) }.getOrNull()
        if (stat != null && stat.availableBytes < 50L * 1024L * 1024L) {
            return "STORAGE_LOW" to "可用存储不足"
        }
        return null
    }

    private fun failTask(taskId: String, code: String, message: String, waitingUser: Boolean = false) {
        store.finish(taskId, false, code)
        runtimeStatus.updateTask(
            taskId,
            if (waitingUser) AuthorizedTaskState.WaitingConfirmation else AuthorizedTaskState.Failed,
            message,
            code,
        )
    }

    private suspend fun outboxLoop() {
        val configured = loadConnection() ?: return
        val client = CloudTaskClient(configured.first)
        while (scope.isActive) {
            try {
                if (networkAvailability.isValidated()) {
                    flushOutbox(client)
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                // Upload failures must not stop local execution or lease renewal.
            }
            delay(OUTBOX_POLL_INTERVAL_MILLIS)
        }
    }

    private suspend fun flushOutbox(client: CloudTaskClient) {
        for (outbox in store.dueEventsByTask()) {
            try {
                withContext(Dispatchers.IO) { client.post(outbox.path, outbox.payload) }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: CloudHttpException) {
                when (OutboxRetryPolicy.classify(error)) {
                    DeliveryFailureAction.ACCEPT_AS_DELIVERED -> store.markDelivered(outbox.id)
                    DeliveryFailureAction.PERMANENT_REJECTION -> {
                        store.markPermanentlyRejected(outbox.id, "HTTP_${error.status}")
                        continue
                    }
                    DeliveryFailureAction.RETRY -> {
                        store.recordDeliveryFailure(
                            outbox.id,
                            "HTTP_${error.status}",
                            OutboxRetryPolicy.nextAttemptAt(outbox.id, outbox.attemptCount + 1),
                        )
                        continue
                    }
                }
                continue
            } catch (error: Exception) {
                store.recordDeliveryFailure(
                    outbox.id,
                    error.javaClass.simpleName,
                    OutboxRetryPolicy.nextAttemptAt(outbox.id, outbox.attemptCount + 1),
                )
                continue
            }
            store.markDelivered(outbox.id)
        }
    }

    private fun persistPaused(
        taskId: String,
        pending: PendingTask,
        paused: TaskPausedException,
    ) {
        val payload = JSONObject(pending.payload)
        val previous = store.latestCheckpoint(taskId)
        val cursor = if (paused.lastCompletedStepIndex >= 0) {
            paused.lastCompletedStepIndex
        } else {
            previous?.optInt("loopCursor", -1) ?: -1
        }
        val stepId = paused.lastCompletedStepId
            ?: previous?.optString("itemId")?.takeIf { it.isNotBlank() }
            ?: "preflight"
        val recipeHash = ClaimedTaskInterpreter.recipeHash(payload).ifBlank {
            payload.optString("recipeSha256").ifBlank { previous?.optString("recipeHash").orEmpty().ifBlank { "recipe" } }
        }
        store.saveCheckpoint(
            taskId,
            pending.leaseId,
            stepId,
            "pause",
            recipeHash,
            ClaimedTaskInterpreter.accountId(payload).ifBlank { payload.optString("deviceId") },
            ClaimedTaskInterpreter.bindingVersion(payload).takeIf { it > 0 }
                ?: previous?.optInt("bindingVersion", 0)
                ?: 0,
            cursor,
            paused.lastCompletedStepId ?: previous?.optString("itemId")?.takeIf { it.isNotBlank() },
        )
        store.markPaused(
            taskId,
            paused.lastCompletedStepId,
            paused.lastCompletedStepIndex,
            paused.message,
        )
        runtimeStatus.updateTask(
            taskId,
            AuthorizedTaskState.WaitingConfirmation,
            "已在安全点暂停，等待人工接管",
            "PAUSED_WAITING_USER",
            paused.lastCompletedStepId,
        )
    }

    private fun throwIfControlRequested(control: ExecutionControl) {
        when {
            control.cancelRequested -> throw ExecutorFailure("CANCELLED", control.reason ?: "Task was cancelled")
            control.pauseRequested -> throw TaskPausedException(null, -1, control.reason)
        }
    }

    private fun applyHeartbeatControl(control: ExecutionControl, heartbeat: TaskHeartbeat) {
        when (heartbeat.businessState) {
            "CANCEL_REQUESTED" -> control.requestCancel(heartbeat.stallReason)
            "PAUSE_REQUESTED" -> control.requestPause(heartbeat.stallReason)
        }
    }

    private suspend fun runTaskHeartbeats(
        client: CloudTaskClient,
        taskId: String,
        leaseId: String,
        control: ExecutionControl,
        currentStep: AtomicInteger,
    ) {
        val heartbeatRetry = SyncRetryPolicy(
            initialDelayMillis = HEARTBEAT_RETRY_INITIAL_MILLIS,
            maximumDelayMillis = HEARTBEAT_RETRY_MAXIMUM_MILLIS,
        )
        while (currentCoroutineContext().isActive) {
            delay(HEARTBEAT_INTERVAL_MILLIS)
            var delivered = false
            while (currentCoroutineContext().isActive && !delivered) {
                try {
                    networkAvailability.awaitValidated()
                    val heartbeat = client.heartbeat(
                        taskId,
                        leaseId,
                        currentStep.get().takeIf { it >= 0 },
                    )
                    applyHeartbeatControl(control, heartbeat)
                    heartbeatRetry.reset()
                    delivered = true
                } catch (error: CloudHttpException) {
                    if (error.status == 409) {
                        throw ExecutorFailure("LEASE_FENCED", "stale lease or control epoch rejected")
                    }
                    if (!error.retryable) throw error
                    delay(heartbeatRetry.nextDelayMillis())
                } catch (_: IOException) {
                    delay(heartbeatRetry.nextDelayMillis())
                }
            }
        }
    }

    private suspend fun sendInitialHeartbeat(
        client: CloudTaskClient,
        taskId: String,
        leaseId: String,
        control: ExecutionControl,
    ) {
        try {
            val heartbeat = withContext(Dispatchers.IO) { client.heartbeat(taskId, leaseId, null) }
            applyHeartbeatControl(control, heartbeat)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: CloudHttpException) {
            if (error.status == 409) {
                throw ExecutorFailure("LEASE_FENCED", "stale lease or control epoch rejected")
            }
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

    /** B17: lazily builds the shared control-plane runtime once a binding exists. */
    private fun controlRuntime(): ControlRuntime? {
        controlRuntime?.let { return it }
        val configured = loadConnection() ?: return null
        val state = ControlStateStore(store)
        val client = ControlSyncClient(PinnedControlPlaneTransport(configured.first), state)
        val runtime = ControlRuntime(
            state = state,
            client = client,
            orchestrator = ControlLoopOrchestrator(
                syncClient = client,
                state = state,
                pausedHead = { store.pausedHeadInfo() },
                suspectPolicy = SuspectOrphanedPolicy(),
                onSuspectOrphaned = { signal ->
                    // §3.3: alert + forced control sync + snapshot reconcile +
                    // block destructive claims. Never clears the PAUSED blocker.
                    android.util.Log.w(
                        "CompanionSync",
                        "SUSPECT_ORPHANED task=${signal.taskId} pausedSince=${signal.pausedSince} " +
                            "controlLag=${signal.controlLag}",
                    )
                    runtimeStatus.markSuspectOrphaned(
                        signal.taskId,
                        "PAUSED since ${signal.pausedSince}; control watermark lag ${signal.controlLag}; " +
                            "awaiting server-authoritative resolution",
                    )
                    suspectForceSnapshot = true
                },
            ),
        )
        controlRuntime = runtime
        return runtime
    }

    /** §2.3 safetyBarrier: unresolved ledger rows outweigh the suspect alert. */
    private fun currentSafetyBarrier(): String = when {
        store.unresolvedControlledActionKeys().isNotEmpty() -> "RECONCILING"
        suspectActive -> "UNKNOWN"
        else -> "NONE"
    }

    private fun parseInlineControlEvents(response: JSONObject): List<ControlEvent> {
        val array = response.optJSONArray("inlineEvents") ?: return emptyList()
        return buildList {
            for (index in 0 until array.length()) {
                runCatching { add(ControlPlaneJson.parseControlEvent(array.getJSONObject(index))) }
            }
        }
    }

    private fun createNotificationChannel() {
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Cloud task execution", NotificationManager.IMPORTANCE_LOW),
        )
    }

    private companion object {
        const val CHANNEL_ID = "cloudctl_sync"
        const val NOTIFICATION_ID = 1001
        const val HEARTBEAT_INTERVAL_MILLIS = 2_000L
        const val DEVICE_HEARTBEAT_INTERVAL_MILLIS = 20_000L
        const val HEARTBEAT_RETRY_INITIAL_MILLIS = 1_000L
        const val HEARTBEAT_RETRY_MAXIMUM_MILLIS = 10_000L
        const val IDLE_POLL_INTERVAL_MILLIS = 2_000L
        const val OUTBOX_POLL_INTERVAL_MILLIS = 1_000L
        const val ACCESSIBILITY_RUNTIME_WAIT_MILLIS = 3_000L
        const val ACCESSIBILITY_RUNTIME_POLL_MILLIS = 100L
        // Two attempts keep the worst-case window (2 x 45s transport timeout +
        // 1s backoff) inside the 60s task lease; attempt 3 would already race
        // lease expiry into LEASE_FENCED.
        const val FRESH_HEARTBEAT_ATTEMPTS = 2

        /** IM body enrichment: at most 3 backward swipes, stop at the first readable inbound. */
        const val ENRICH_SWIPE_ATTEMPTS = 3
        const val ENRICH_SWIPE_SETTLE_MS = 600L
    }
}
