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
import com.company.cloudctl.companion.automation.RecipeEngine
import com.company.cloudctl.companion.automation.RecipePackage
import com.company.cloudctl.companion.automation.ResumeValidator
import com.company.cloudctl.companion.automation.TargetLocatorRegistry
import com.company.cloudctl.companion.automation.TaskPausedException
import com.company.cloudctl.companion.data.AutomationStore
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
import com.company.cloudctl.companion.network.PreviewGrant
import com.company.cloudctl.companion.network.ResumeCommand
import com.company.cloudctl.companion.network.DeliveryFailureAction
import com.company.cloudctl.companion.network.OutboxRetryPolicy
import com.company.cloudctl.companion.network.NetworkAvailability
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

class CompanionSyncService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
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

    override fun onCreate() {
        super.onCreate()
        store = AutomationStore(this)
        runtimeStatus = RuntimeStatusStore(this)
        networkAvailability = NetworkAvailability(this)
        mediaDeliveryCoordinator = MediaDeliveryCoordinator(this)
        store.recoverInterruptedRuns()
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
                    android.util.Log.d("CompanionSync", "Sending heartbeat payload: $payload")
                    val heartbeat = withContext(Dispatchers.IO) { client.deviceHeartbeat(payload) }
                    android.util.Log.i("CompanionSync", "Heartbeat successful")
                    runtimeStatus.markPresence(true)
                    retryPolicy.reset()
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
                    if (!store.hasBlockingHead()) claimed = withContext(Dispatchers.IO) { client.claim() }
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
        val command = runCatching { ClaimedTaskInterpreter.commandOrNull(pending.payload) }
            .getOrElse {
                failTask(pending.taskId, "TASK_CONTRACT_REJECTED", "任务指令校验未通过")
                return true
            }
        if (command != null) {
            return runCommandV1(client, pending, command)
        }
        val task = runCatching { AutomationTaskParser.parse(pending.payload) }
            .getOrElse {
                failTask(pending.taskId, "TASK_CONTRACT_REJECTED", "任务指令校验未通过")
                return true
            }
        val stall = preflightStallReason()
        if (stall != null) {
            failTask(task.taskId, stall.first, stall.second, waitingUser = stall.first == "DEVICE_LOCKED")
            return true
        }
        val control = ExecutionControl()
        val service = CloudCtlAccessibilityService.active
        if (service == null) {
            failTask(task.taskId, "ACCESSIBILITY_NOT_ENABLED", "无障碍服务未启用")
            return true
        }
        val commitGate = buildStepsPublishGate(service, task)
        try {
            sendInitialHeartbeat(client, task.taskId, pending.leaseId, control)
            throwIfControlRequested(control)
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
                    service.launchTargetApp(task.targetPackage)
                    throwIfControlRequested(control)
                    runtimeStatus.updateTask(
                        task.taskId,
                        AuthorizedTaskState.Running,
                        "正在启动本地执行器",
                        "TASK_STARTED",
                    )
                    withTimeout(task.maxRunSeconds * 1_000L) {
                        service.execute(task, control, startAfterIndex = -1, commitGate = commitGate) { step, state ->
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
            persistPaused(task.taskId, pending, paused)
        } catch (cancelled: CancellationException) {
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
                persistPaused(task.taskId, pending, TaskPausedException(null, -1, control.reason))
                return true
            }
            val waiting = failure.code in setOf("UNKNOWN_PAGE", "LAUNCH_REQUIRES_USER", "DEVICE_LOCKED")
            failTask(task.taskId, failure.code, failure.message ?: failure.code, waitingUser = waiting)
        } catch (error: Exception) {
            if (control.pauseRequested) {
                persistPaused(task.taskId, pending, TaskPausedException(null, -1, control.reason))
                return true
            }
            failTask(task.taskId, "TASK_EXECUTION_FAILED", error.message ?: "本地任务已安全终止")
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
        val service = CloudCtlAccessibilityService.active
        if (service == null) {
            failTask(task.taskId, "ACCESSIBILITY_NOT_ENABLED", "无障碍服务未启用")
            return
        }
        val commitGate = buildStepsPublishGate(service, task)
        val checkpoint = store.latestCheckpoint(task.taskId)
        if (checkpoint == null) {
            persistPaused(task.taskId, pending, TaskPausedException(null, -1, "resume checkpoint missing"))
            return
        }
        val control = ExecutionControl()
        val startAfterIndex = checkpoint.optInt("loopCursor", -1)
        try {
            service.launchTargetApp(task.targetPackage)
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
                        service.execute(task, control, startAfterIndex, commitGate = commitGate) { step, state ->
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
            persistPaused(task.taskId, pending, paused)
        } catch (cancelled: CancellationException) {
            store.finish(task.taskId, false, "CANCELLED")
            runtimeStatus.updateTask(task.taskId, AuthorizedTaskState.Canceled, "任务已取消", "CANCELLED")
            throw cancelled
        } catch (failure: ExecutorFailure) {
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
                persistPaused(
                    task.taskId,
                    pending,
                    TaskPausedException(checkpoint.optString("itemId").ifBlank { null }, startAfterIndex, failure.message),
                )
                return
            }
            if (control.pauseRequested) {
                persistPaused(task.taskId, pending, TaskPausedException(null, -1, control.reason))
                return
            }
            failTask(task.taskId, failure.code, failure.message ?: failure.code)
        } catch (error: Exception) {
            if (control.pauseRequested) {
                persistPaused(task.taskId, pending, TaskPausedException(null, -1, control.reason))
                return
            }
            failTask(task.taskId, "TASK_EXECUTION_FAILED", error.message ?: "本地任务已安全终止")
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
    ): Boolean {
        val stall = preflightStallReason()
        if (stall != null) {
            failTask(command.taskId, stall.first, stall.second, waitingUser = stall.first == "DEVICE_LOCKED")
            return true
        }
        val service = CloudCtlAccessibilityService.active
        if (service == null) {
            failTask(command.taskId, "ACCESSIBILITY_NOT_ENABLED", "无障碍服务未启用")
            return true
        }
        val control = ExecutionControl()
        val checkpoint = store.latestCheckpoint(command.taskId)
        var recipeProgress: RecipeResumeProgress? = null
        var parsedRecipe: RecipePackage? = null
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
            sendInitialHeartbeat(client, command.taskId, pending.leaseId, control)
            throwIfControlRequested(control)
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
                    service.launchTargetApp(command.targetPackage)
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
            val progress = recipeProgress
            val recipe = parsedRecipe
            if (progress?.nextStateId != null && recipe != null) {
                persistRecipePaused(command, recipe, progress, paused.message)
            } else {
                persistPaused(command.taskId, pending, paused)
            }
        } catch (cancelled: CancellationException) {
            store.finish(command.taskId, false, "CANCELLED")
            runtimeStatus.updateTask(command.taskId, AuthorizedTaskState.Canceled, "任务已取消", "CANCELLED")
            throw cancelled
        } catch (failure: ExecutorFailure) {
            if (resume != null && (
                    failure.code.startsWith("RESUME_") || failure.code in setOf(
                    "WRONG_ACTIVE_PACKAGE",
                    "ACTIVE_WINDOW_MISSING",
                    "APP_NOT_FOREGROUND",
                    "ACCESSIBILITY_NOT_ACTIVE",
                    )
                )
            ) {
                persistResumeRejected(command.taskId, checkpoint, failure.message)
                return true
            }
            if (control.cancelRequested) {
                store.finish(command.taskId, false, "CANCELLED")
                runtimeStatus.updateTask(command.taskId, AuthorizedTaskState.Canceled, "任务已取消", "CANCELLED")
                return true
            }
            if (control.pauseRequested) {
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
                persistPaused(command.taskId, pending, TaskPausedException(null, -1, control.reason))
                return true
            }
            failTask(command.taskId, "TASK_EXECUTION_FAILED", error.message ?: "本地任务已安全终止")
        } finally {
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

    private fun preflightStallReason(): Pair<String, String>? {
        if (!accessibilityEnabled()) return "ACCESSIBILITY_NOT_ENABLED" to "无障碍服务未启用"
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
    }
}
