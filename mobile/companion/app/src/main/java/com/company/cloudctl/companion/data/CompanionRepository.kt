package com.company.cloudctl.companion.data

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import com.company.cloudctl.companion.device.LocalHealthCollector
import com.company.cloudctl.companion.model.AuthorizedTaskState
import com.company.cloudctl.companion.model.CompanionState
import com.company.cloudctl.companion.model.DeviceBinding
import com.company.cloudctl.companion.model.EnrollmentPayload
import com.company.cloudctl.companion.model.LocalOperationStatus
import com.company.cloudctl.companion.model.PermissionState
import com.company.cloudctl.companion.model.ArtifactDeliveryState
import com.company.cloudctl.companion.model.ArtifactDeliveryStatus
import com.company.cloudctl.companion.model.ArtifactKind
import com.company.cloudctl.companion.network.CloudConnection
import com.company.cloudctl.companion.network.CloudTaskClient
import com.company.cloudctl.companion.network.CompanionCloudClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import com.company.cloudctl.companion.operations.OperationDefinition
import com.company.cloudctl.companion.security.SecretStore
import com.company.cloudctl.companion.service.BatteryOptimization
import com.company.cloudctl.companion.service.CompanionServiceStarter
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONObject
import java.time.Instant
import java.util.UUID

class CompanionRepository(
    private val context: Context,
    private val cloudClient: CompanionCloudClient,
    private val secretStore: SecretStore = SecretStore(context),
    private val healthCollector: LocalHealthCollector = LocalHealthCollector(context),
    private val runtimeStatusStore: RuntimeStatusStore = RuntimeStatusStore(context),
    private val localOperationStore: LocalOperationStore = LocalOperationStore(context),
    private val artifactDeliveryStore: ArtifactDeliveryStore = ArtifactDeliveryStore(context),
    private val mediaDeliveryCoordinator: MediaDeliveryCoordinator = MediaDeliveryCoordinator(context, artifactDeliveryStore),
) {
    private val preferences = context.getSharedPreferences("cloudctl_binding", Context.MODE_PRIVATE)
    private val mutableState = MutableStateFlow(
        CompanionState(
            binding = readBinding(),
            permissions = permissionState(),
            localOperations = localOperationStore.snapshot().map(::toLocalOperationStatus),
            deliveries = artifactDeliveryStore.snapshot(),
        ),
    )
    val state: StateFlow<CompanionState> = mutableState.asStateFlow()

    init {
        if (mutableState.value.binding != null) CompanionServiceStarter.startIfBound(context)
    }

    suspend fun enroll(payload: EnrollmentPayload) = runOperation {
        val result = cloudClient.enroll(payload, appInstanceId())
        saveBinding(result.binding)
        secretStore.put(BINDING_TOKEN, result.bindingToken)
        CompanionServiceStarter.startIfBound(context)
        it.copy(binding = result.binding, emergencyStopped = false)
    }

    suspend fun refresh() = runOperation { current ->
        val localHealth = healthCollector.collect()
        val runtime = runtimeStatusStore.snapshot()
        current.copy(
            health = localHealth,
            permissions = permissionState(),
            task = runtime.task,
            logs = runtime.logs,
            localOperations = localOperationStore.snapshot().map(::toLocalOperationStatus),
            presenceOnline = runtime.presenceOnline,
            deliveries = artifactDeliveryStore.snapshot(),
            accountStatuses = loadAccountStatuses(current),
        )
    }

    suspend fun downloadMedia(deliveryId: String, assetIds: List<String>) = runOperation { current ->
        val binding = current.binding ?: error("Device is not enrolled")
        val token = token() ?: error("Missing binding token")
        mediaDeliveryCoordinator.deliver(CloudConnection(binding.cloudUrl, token, binding.certificateSha256), deliveryId, assetIds)
        current.copy(deliveries = artifactDeliveryStore.snapshot(), error = null)
    }

    suspend fun enqueuePlaceholderOperation(
        definition: OperationDefinition,
        parameters: Map<String, String> = emptyMap()
    ) = runOperation { current ->
        if (definition.key == "product.publish") {
            val binding = current.binding ?: error("Device is not enrolled")
            val token = token() ?: error("Missing binding token")
            
            // Extract parameters with defaults
            val description = parameters["description"] ?: DEFAULT_LISTING_DESCRIPTION
            val price = parameters["price"] ?: DEFAULT_LISTING_PRICE
            val autoPublish = parameters["autoPublish"]?.toBoolean() ?: true
            val mediaAssetIds = parameters["mediaAssetIds"]?.split(",")?.filter { it.isNotBlank() }
            val deliveryId = parameters["deliveryId"]
            
            val response = withContext(Dispatchers.IO) {
                CloudTaskClient(
                    CloudConnection(binding.cloudUrl, token, binding.certificateSha256),
                ).requestTextPublish(
                    description = description,
                    price = price,
                    autoPublish = autoPublish,
                    mediaAssetIds = mediaAssetIds,
                    deliveryId = deliveryId
                )
            }
            
            val taskId = response.optString("taskId")
            val publishStatus = if (autoPublish) "自动发布" else "填写表单"
            val mediaInfo = if (mediaAssetIds != null && mediaAssetIds.isNotEmpty()) {
                "，包含 ${mediaAssetIds.size} 个媒体文件"
            } else ""
            
            localOperationStore.enqueue(
                definition,
                mapOf("taskId" to taskId),
                state = "QUEUED",
                detail = "已向云端申请闲鱼发布任务 $taskId ($publishStatus$mediaInfo)",
            )
        } else {
            localOperationStore.enqueue(definition)
        }
        current.copy(
            localOperations = localOperationStore.snapshot().map(::toLocalOperationStatus),
            error = null,
        )
    }

    fun toggleState(key: String): Boolean = localOperationStore.toggleState(key)

    suspend fun setToggle(definition: OperationDefinition, enabled: Boolean) = runOperation { current ->
        localOperationStore.setToggleState(definition.key, enabled)
        localOperationStore.enqueue(definition, mapOf("enabled" to enabled.toString()))
        current.copy(
            localOperations = localOperationStore.snapshot().map(::toLocalOperationStatus),
            error = null,
        )
    }

    suspend fun emergencyStop() = runOperation { current ->
        current.binding ?: error("Device is not enrolled")
        current.copy(
            emergencyStopped = true,
            task = current.task?.copy(
                state = AuthorizedTaskState.Stopping,
                step = "Emergency stop requested",
                cancellable = false,
            ),
            confirmation = null,
        )
    }

    suspend fun answerConfirmation(@Suppress("UNUSED_PARAMETER") approved: Boolean) = runOperation { current ->
        error("Cloud confirmation is not part of the mobile v2 execution contract")
    }

    suspend fun unbind() = runOperation { current ->
        val binding = current.binding ?: error("Device is not enrolled")
        val bindingToken = token() ?: error("Binding token is unavailable; unbind is unsafe")
        revokeThenClear(
            revoke = { cloudClient.unbind(binding, bindingToken) },
            clear = {
                preferences.edit().remove(BINDING).apply()
                secretStore.clear(BINDING_TOKEN)
            },
        )
        CompanionState(permissions = permissionState())
    }

    fun reportError(error: Throwable) {
        mutableState.value = mutableState.value.copy(
            busy = false,
            error = error.message ?: "Operation failed",
        )
    }

    private suspend fun runOperation(transform: suspend (CompanionState) -> CompanionState) {
        mutableState.value = mutableState.value.copy(busy = true, error = null)
        mutableState.value = try {
            transform(mutableState.value).copy(busy = false, error = null)
        } catch (error: Exception) {
            mutableState.value.copy(busy = false, error = error.message ?: "Operation failed")
        }
    }

    private fun saveBinding(binding: DeviceBinding) {
        preferences.edit().putString(
            BINDING,
            JSONObject()
                .put("bindingId", binding.bindingId)
                .put("deviceId", binding.deviceId)
                .put("tenantName", binding.tenantName)
                .put("siteName", binding.siteName)
                .put("cloudUrl", binding.cloudUrl)
                .put("certificateSha256", binding.certificateSha256)
                .toString(),
        ).apply()
    }

    private suspend fun loadAccountStatuses(current: CompanionState) = runCatching {
        val binding = current.binding ?: return@runCatching emptyList()
        val token = token() ?: return@runCatching emptyList()
        cloudClient.accountStatus(binding, token)
    }.getOrDefault(current.accountStatuses)

    private fun readBinding(): DeviceBinding? = preferences.getString(BINDING, null)?.let { encoded ->
        runCatching {
            val value = JSONObject(encoded)
            DeviceBinding(
                bindingId = value.optString("bindingId"),
                deviceId = value.getString("deviceId"),
                tenantName = value.getString("tenantName"),
                siteName = value.getString("siteName"),
                cloudUrl = value.optString("cloudUrl", value.optString("edgeUrl")),
                certificateSha256 = value.getString("certificateSha256"),
            )
        }.getOrNull()
    }

    private fun token(): String? = secretStore.get(BINDING_TOKEN)

    private fun toLocalOperationStatus(value: com.company.cloudctl.companion.operations.OperationReceipt) =
        LocalOperationStatus(
            id = value.id,
            operationKey = value.operationKey,
            title = value.title,
            module = value.module,
            state = value.state,
            detail = value.detail,
            createdAt = runCatching { Instant.parse(value.createdAt) }.getOrDefault(Instant.EPOCH),
        )

    private fun appInstanceId(): String {
        val existing = preferences.getString(APP_INSTANCE_ID, null)
        if (existing != null) return existing
        return UUID.randomUUID().toString().also {
            preferences.edit().putString(APP_INSTANCE_ID, it).commit()
        }
    }

    private fun permissionState(): PermissionState {
        val notificationsGranted = Build.VERSION.SDK_INT < 33 ||
            context.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED
        return PermissionState(
            notificationsGranted = notificationsGranted,
            lamdaServiceCertificateEnabled = accessibilityEnabled(),
            batteryOptimizationIgnored = BatteryOptimization.isIgnoring(context),
            automationProfile = when {
                Build.TAGS?.contains("test-keys") == true -> "Lab profile"
                else -> "Standard authorized profile"
            },
        )
    }

    private fun accessibilityEnabled(): Boolean {
        val enabled = Settings.Secure.getString(
            context.contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
        ).orEmpty()
        val packageName = context.packageName
        val relative = ".automation.CloudCtlAccessibilityService"
        val candidates = setOf(
            "$packageName/$packageName$relative",
            "$packageName/$relative",
        )
        return enabled.split(':').any { candidates.any { candidate -> it.equals(candidate, ignoreCase = true) } }
    }

    private companion object {
        const val BINDING = "binding"
        const val BINDING_TOKEN = "binding_token"
        const val APP_INSTANCE_ID = "app_instance_id"
        const val DEFAULT_LISTING_DESCRIPTION = "自用闲置，功能正常，支持当面交易"
        const val DEFAULT_LISTING_PRICE = "128"
    }
}

internal suspend fun revokeThenClear(revoke: suspend () -> Unit, clear: () -> Unit) {
    revoke()
    clear()
}
