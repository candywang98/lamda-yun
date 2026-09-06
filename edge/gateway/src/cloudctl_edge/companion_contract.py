from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class AuthorizedTaskState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    STOPPING = "STOPPING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    UNKNOWN = "UNKNOWN"


class ArtifactKind(StrEnum):
    APK = "APK"
    APK_SPLIT = "APK_SPLIT"
    MEDIA = "MEDIA"
    AUTOMATION_PACKAGE = "AUTOMATION_PACKAGE"


class ArtifactDeliveryState(StrEnum):
    QUEUED = "QUEUED"
    DOWNLOADING = "DOWNLOADING"
    VERIFIED = "VERIFIED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


class OperatorActionType(StrEnum):
    CONFIRM = "CONFIRM"
    REJECT = "REJECT"
    STOP_AUTOMATION = "STOP_AUTOMATION"


class ConfirmationRiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class AuthorizedTaskStatus:
    task_run_id: str
    command_id: str
    state: AuthorizedTaskState
    step: str
    cancellable: bool
    confirmation_id: str | None = None

    def to_wire(self) -> dict[str, object]:
        return {
            "taskRunId": self.task_run_id,
            "commandId": self.command_id,
            "state": self.state.value,
            "step": self.step,
            "cancellable": self.cancellable,
            "confirmationId": self.confirmation_id,
        }


@dataclass(frozen=True, slots=True)
class PublicDeviceHealth:
    lamda_state: str
    edge_state: str
    target_app_version: str
    battery_percent: int
    charging: bool
    network: str
    temperature_celsius: float | None
    free_storage_bytes: int
    companion_version: str
    observed_at: datetime

    def __post_init__(self) -> None:
        if not 0 <= self.battery_percent <= 100:
            raise ValueError("battery_percent must be between 0 and 100")
        if self.free_storage_bytes < 0:
            raise ValueError("free_storage_bytes cannot be negative")

    def to_wire(self) -> dict[str, object]:
        return {
            "lamdaState": self.lamda_state,
            "edgeState": self.edge_state,
            "targetAppVersion": self.target_app_version,
            "batteryPercent": self.battery_percent,
            "charging": self.charging,
            "network": self.network,
            "temperatureCelsius": self.temperature_celsius,
            "freeStorageBytes": self.free_storage_bytes,
            "companionVersion": self.companion_version,
            "observedAt": self.observed_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ArtifactDeliveryStatus:
    artifact_id: str
    kind: ArtifactKind
    state: ArtifactDeliveryState
    bytes_received: int
    size_bytes: int
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.bytes_received < 0 or self.size_bytes < 0:
            raise ValueError("artifact byte counts cannot be negative")
        if self.bytes_received > self.size_bytes:
            raise ValueError("artifact bytes_received exceeds size_bytes")

    def to_wire(self) -> dict[str, object]:
        progress = 100 if self.size_bytes == 0 else self.bytes_received * 100 // self.size_bytes
        return {
            "artifactId": self.artifact_id,
            "kind": self.kind.value,
            "state": self.state.value,
            "bytesReceived": self.bytes_received,
            "sizeBytes": self.size_bytes,
            "progressPercent": progress,
            "errorCode": self.error_code,
        }


@dataclass(frozen=True, slots=True)
class ConfirmationPrompt:
    confirmation_id: str
    title: str
    detail: str
    risk_level: ConfirmationRiskLevel
    expires_at: datetime

    def to_wire(self) -> dict[str, object]:
        return {
            "id": self.confirmation_id,
            "title": self.title,
            "detail": self.detail,
            "riskLevel": self.risk_level.value,
            "expiresAt": self.expires_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class CompanionSnapshot:
    health: PublicDeviceHealth
    task: AuthorizedTaskStatus | None
    confirmation: ConfirmationPrompt | None
    deliveries: tuple[ArtifactDeliveryStatus, ...] = ()
    automation_stopped: bool = False

    def to_wire(self) -> dict[str, object]:
        return {
            "health": self.health.to_wire(),
            "task": None if self.task is None else self.task.to_wire(),
            "confirmation": (None if self.confirmation is None else self.confirmation.to_wire()),
            "deliveries": [delivery.to_wire() for delivery in self.deliveries],
            "currentTask": None if self.task is None else self.task.task_run_id,
            "automationStopped": self.automation_stopped,
        }
