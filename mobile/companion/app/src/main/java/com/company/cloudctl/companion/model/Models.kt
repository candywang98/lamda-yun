package com.company.cloudctl.companion.model

import java.time.Instant

data class EnrollmentPayload(
    val cloudUrl: String,
    val code: String,
    val certificateSha256: String,
)

data class DeviceBinding(
    val bindingId: String,
    val deviceId: String,
    val tenantName: String,
    val siteName: String,
    val cloudUrl: String,
    val certificateSha256: String,
)

data class AccountAuthorizationStatus(
    val accountId: String,
    val platform: String,
    val displayLabel: String,
    val status: String,
    val authorized: Boolean,
    val expiresAt: String? = null,
    val lastCheckedAt: String? = null,
    val boundToDevice: Boolean,
)

data class DeviceHealth(
    val lamdaState: ServiceState = ServiceState.Unknown,
    val edgeState: ServiceState = ServiceState.Unknown,
    val executorVersion: String = "-",
    val batteryPercent: Int = 0,
    val charging: Boolean = false,
    val network: String = "Offline",
    val temperatureCelsius: Float? = null,
    val freeStorageBytes: Long = 0,
    val companionVersion: String = "-",
    val observedAt: Instant = Instant.EPOCH,
)

enum class ServiceState { Healthy, Degraded, Offline, Unknown }

data class PermissionState(
    val notificationsGranted: Boolean = false,
    val lamdaServiceCertificateEnabled: Boolean = false,
    val batteryOptimizationIgnored: Boolean = false,
    val inputMethodEnabled: Boolean = false,
    val inputMethodCurrent: Boolean = false,
    val automationProfile: String = "Not detected",
)

enum class ConfirmationRiskLevel { Low, Medium, High, Critical, Unknown }

data class ConfirmationRequest(
    val id: String,
    val title: String,
    val detail: String,
    val riskLevel: ConfirmationRiskLevel = ConfirmationRiskLevel.Unknown,
    val expiresAt: Instant,
)

enum class AuthorizedTaskState {
    Queued,
    Running,
    WaitingConfirmation,
    Stopping,
    Succeeded,
    Failed,
    Canceled,
    Unknown,
}

data class AuthorizedTaskStatus(
    val taskRunId: String,
    val commandId: String = "",
    val state: AuthorizedTaskState = AuthorizedTaskState.Unknown,
    val step: String = "",
    val cancellable: Boolean = false,
    val confirmationId: String? = null,
)

data class LocalRunLog(
    val taskId: String,
    val stepId: String?,
    val state: String,
    val detailCode: String,
    val occurredAt: Instant,
)

data class LocalOperationStatus(
    val id: String,
    val operationKey: String,
    val title: String,
    val module: String,
    val state: String,
    val detail: String,
    val createdAt: Instant,
)

enum class ArtifactKind { Apk, ApkSplit, Media, AutomationPackage, Unknown }

enum class ArtifactDeliveryState { Queued, Downloading, Verified, Delivered, Failed, Unknown }

data class ArtifactDeliveryStatus(
    val artifactId: String,
    val deliveryId: String = "",
    val kind: ArtifactKind = ArtifactKind.Unknown,
    val state: ArtifactDeliveryState = ArtifactDeliveryState.Unknown,
    val bytesReceived: Long = 0,
    val sizeBytes: Long = 0,
    val progressPercent: Int = 0,
    val errorCode: String? = null,
    val localUri: String? = null,
)

data class UpdateState(
    val currentVersion: String,
    val availableVersion: String? = null,
    val signerVerified: Boolean = false,
)

data class CompanionState(
    val binding: DeviceBinding? = null,
    val health: DeviceHealth = DeviceHealth(),
    val permissions: PermissionState = PermissionState(),
    val confirmation: ConfirmationRequest? = null,
    val update: UpdateState = UpdateState(currentVersion = "0.1.0"),
    val task: AuthorizedTaskStatus? = null,
    val logs: List<LocalRunLog> = emptyList(),
    val localOperations: List<LocalOperationStatus> = emptyList(),
    val deliveries: List<ArtifactDeliveryStatus> = emptyList(),
    val accountStatuses: List<AccountAuthorizationStatus> = emptyList(),
    val emergencyStopped: Boolean = false,
    val presenceOnline: Boolean = false,
    val busy: Boolean = false,
    val error: String? = null,
)
