from __future__ import annotations

from enum import StrEnum


class DriverErrorCode(StrEnum):
    CONNECTION_FAILED = "DEVICE_CONNECTION_FAILED"
    CERTIFICATE_REJECTED = "DEVICE_CERTIFICATE_REJECTED"
    IDENTITY_MISMATCH = "DEVICE_IDENTITY_MISMATCH"
    LOCK_UNAVAILABLE = "DEVICE_LOCK_UNAVAILABLE"
    LOCK_LOST = "DEVICE_LOCK_LOST"
    STALE_FENCE = "DEVICE_STALE_FENCE"
    DEADLINE_EXCEEDED = "DEVICE_DEADLINE_EXCEEDED"
    ELEMENT_NOT_FOUND = "DEVICE_ELEMENT_NOT_FOUND"
    CAPABILITY_DENIED = "DEVICE_CAPABILITY_DENIED"
    APK_POLICY_REJECTED = "APK_POLICY_REJECTED"
    APK_INSTALL_FAILED = "APK_INSTALL_FAILED"
    APK_COMMIT_UNKNOWN = "APK_COMMIT_UNKNOWN"
    IO_FAILED = "DEVICE_IO_FAILED"
    UNKNOWN = "DEVICE_UNKNOWN"


class DeviceDriverError(RuntimeError):
    def __init__(
        self,
        code: DriverErrorCode,
        detail: str,
        *,
        retryable: bool,
        reconcile_required: bool = False,
    ):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.retryable = retryable
        self.reconcile_required = reconcile_required


def map_exception(exc: Exception) -> DeviceDriverError:
    if isinstance(exc, DeviceDriverError):
        return exc
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in name or "deadline" in message:
        return DeviceDriverError(
            DriverErrorCode.DEADLINE_EXCEEDED, "device operation timed out", retryable=True
        )
    if "certificate" in message or "tls" in message or "ssl" in message:
        return DeviceDriverError(
            DriverErrorCode.CERTIFICATE_REJECTED,
            "device service certificate was rejected",
            retryable=False,
        )
    if "lock" in name or "lock" in message:
        return DeviceDriverError(
            DriverErrorCode.LOCK_UNAVAILABLE, "LAMDA API lock is unavailable", retryable=True
        )
    if isinstance(exc, LookupError):
        return DeviceDriverError(
            DriverErrorCode.ELEMENT_NOT_FOUND, "UI element was not found", retryable=False
        )
    if isinstance(exc, PermissionError):
        return DeviceDriverError(
            DriverErrorCode.CAPABILITY_DENIED, "device capability is not permitted", retryable=False
        )
    if isinstance(exc, (ConnectionError, OSError)):
        return DeviceDriverError(
            DriverErrorCode.CONNECTION_FAILED, "device connection failed", retryable=True
        )
    return DeviceDriverError(
        DriverErrorCode.UNKNOWN, "unclassified device driver failure", retryable=False
    )
