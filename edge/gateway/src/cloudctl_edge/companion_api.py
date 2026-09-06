from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from .companion_contract import OperatorActionType
from .operator_actions import OperatorActionCoordinator, OperatorActionError
from .spool import EdgeSpool


class CompanionSupervisor(Protocol):
    def active_command(self, device_id: str) -> str | None: ...


class EnrollmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=4, max_length=128)


class HealthReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batteryPercent: int = Field(ge=0, le=100)
    charging: bool
    network: str = Field(min_length=1, max_length=64)
    temperatureCelsius: float | None = Field(default=None, ge=-50, le=150)
    freeStorageBytes: int = Field(ge=0)
    companionVersion: str = Field(min_length=1, max_length=128)
    observedAt: datetime


class ConfirmationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool


class CompanionAuthStore:
    """One-time enrollment and high-entropy bearer bindings backed by the Edge spool."""

    def __init__(self, spool: EdgeSpool):
        self._spool = spool

    def issue_enrollment_code(
        self,
        *,
        code: str,
        device_id: str,
        tenant_name: str,
        site_name: str,
    ) -> None:
        normalized = self._normalize_code(code)
        self._spool.issue_companion_enrollment(
            code_digest=self._digest("code", normalized),
            device_id=device_id,
            tenant_name=tenant_name,
            site_name=site_name,
        )

    def enroll(self, code: str) -> dict[str, str] | None:
        normalized = self._normalize_code(code)
        token = secrets.token_urlsafe(32)
        enrollment = self._spool.consume_companion_enrollment(
            code_digest=self._digest("code", normalized),
            token_digest=self._digest("token", token),
        )
        if enrollment is None:
            return None
        enrollment["binding_token"] = token
        return enrollment

    def authenticate(self, token: str) -> str | None:
        if len(token) < 32 or len(token) > 256:
            return None
        return self._spool.companion_binding_device(self._digest("token", token))

    def revoke(self, token: str, *, device_id: str) -> bool:
        if len(token) < 32 or len(token) > 256:
            return False
        return self._spool.revoke_companion_binding(
            token_digest=self._digest("token", token),
            device_id=device_id,
        )

    @staticmethod
    def _normalize_code(code: str) -> str:
        normalized = code.strip().upper()
        if not 6 <= len(normalized) <= 32:
            raise ValueError("Enrollment code must contain 6 to 32 characters")
        if not normalized[0].isalnum() or not normalized[-1].isalnum():
            raise ValueError("Enrollment code cannot start or end with a hyphen")
        if "--" in normalized or any(
            character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for character in normalized
        ):
            raise ValueError("Enrollment code contains invalid characters")
        return normalized

    @staticmethod
    def _digest(kind: str, value: str) -> str:
        return hashlib.sha256(f"cloudctl-companion:{kind}:{value}".encode()).hexdigest()


def create_companion_app(
    *,
    spool: EdgeSpool,
    auth_store: CompanionAuthStore,
    operator_actions: OperatorActionCoordinator,
    supervisor: CompanionSupervisor,
    current_version: str,
) -> FastAPI:
    app = FastAPI(title="CloudCtl Edge Companion API", version="1.0.0")

    def authenticated_binding(
        authorization: str | None = Header(default=None),
    ) -> tuple[str, str]:
        scheme, separator, token = (authorization or "").partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token is required")
        device_id = auth_store.authenticate(token)
        if device_id is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Binding token is invalid")
        return device_id, token

    def authenticated_device(binding: tuple[str, str] = Depends(authenticated_binding)) -> str:
        return binding[0]

    def require_bound_device(path_device_id: str, bound_device_id: str) -> None:
        if path_device_id != bound_device_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Binding is for another device")

    @app.post("/companion/v1/enroll")
    async def enroll(request: EnrollmentRequest) -> dict[str, str]:
        try:
            enrollment = auth_store.enroll(request.code)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        if enrollment is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Enrollment code is invalid or consumed")
        return {
            "deviceId": enrollment["device_id"],
            "tenantName": enrollment["tenant_name"],
            "siteName": enrollment["site_name"],
            "bindingToken": enrollment["binding_token"],
        }

    @app.delete(
        "/companion/v1/devices/{device_id}/binding",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def revoke_binding(
        device_id: str,
        binding: tuple[str, str] = Depends(authenticated_binding),
    ) -> Response:
        bound_device_id, token = binding
        require_bound_device(device_id, bound_device_id)
        if not auth_store.revoke(token, device_id=device_id):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Binding token is invalid")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/companion/v1/devices/{device_id}/health", status_code=status.HTTP_204_NO_CONTENT)
    async def report_health(
        device_id: str,
        report: HealthReport,
        bound_device_id: str = Depends(authenticated_device),
    ) -> Response:
        require_bound_device(device_id, bound_device_id)
        current = spool.get_device_health(device_id) or {}
        current.update(
            {
                "battery_percent": report.batteryPercent,
                "charging": report.charging,
                "network_type": report.network,
                "temperature_celsius": report.temperatureCelsius,
                "free_storage_bytes": report.freeStorageBytes,
                "companion_version": report.companionVersion,
                "observed_at": report.observedAt.astimezone(UTC).isoformat(),
            }
        )
        spool.put_device_health(device_id, current)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/companion/v1/devices/{device_id}/snapshot")
    async def snapshot(
        device_id: str,
        bound_device_id: str = Depends(authenticated_device),
    ) -> dict[str, object]:
        require_bound_device(device_id, bound_device_id)
        health = spool.get_device_health(device_id) or {}
        task = _task_snapshot(spool, device_id, supervisor.active_command(device_id))
        confirmation = operator_actions.active_confirmation(device_id)
        automation_stopped = bool(health.get("automation_stopped", False))
        return {
            "health": _health_snapshot(health, current_version),
            "task": task,
            "confirmation": (
                None
                if confirmation is None
                else {
                    "id": confirmation.confirmation_id,
                    "title": confirmation.title,
                    "detail": confirmation.detail,
                    "riskLevel": confirmation.risk_level,
                    "expiresAt": confirmation.expires_at.ToDatetime(tzinfo=UTC).isoformat(),
                }
            ),
            "update": {
                "currentVersion": current_version,
                "availableVersion": None,
                "sha256": "",
                "downloadUrl": "",
                "signature": "",
            },
            "deliveries": spool.artifact_deliveries(device_id),
            "currentTask": None if task is None else task["taskRunId"],
            "automationStopped": automation_stopped,
        }

    @app.post("/companion/v1/confirmations/{confirmation_id}", status_code=status.HTTP_202_ACCEPTED)
    async def answer_confirmation(
        confirmation_id: str,
        answer: ConfirmationAnswer,
        bound_device_id: str = Depends(authenticated_device),
    ) -> dict[str, str]:
        required = operator_actions.active_confirmation(bound_device_id)
        if required is None or required.confirmation_id != confirmation_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Confirmation is not active")
        try:
            await operator_actions.record_local_action(
                action=(
                    OperatorActionType.CONFIRM if answer.approved else OperatorActionType.REJECT
                ),
                device_id=bound_device_id,
                command_id=required.command_id,
                confirmation_id=confirmation_id,
            )
        except OperatorActionError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        return {"state": "ACCEPTED"}

    @app.post(
        "/companion/v1/devices/{device_id}/emergency-stop",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def emergency_stop(
        device_id: str,
        bound_device_id: str = Depends(authenticated_device),
    ) -> dict[str, str]:
        require_bound_device(device_id, bound_device_id)
        command_id = supervisor.active_command(device_id)
        if command_id is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "No active automation is running")
        try:
            await operator_actions.record_local_action(
                action=OperatorActionType.STOP_AUTOMATION,
                device_id=device_id,
                command_id=command_id,
            )
        except OperatorActionError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        health = spool.get_device_health(device_id) or {}
        health["automation_stopped"] = True
        spool.put_device_health(device_id, health)
        return {"state": "STOPPING", "commandId": command_id}

    return app


def _health_snapshot(health: dict[str, object], current_version: str) -> dict[str, object]:
    observed_at = health.get("observed_at") or datetime.now(UTC).isoformat()
    app_versions = health.get("app_versions")
    target_version = "-"
    if isinstance(app_versions, dict) and app_versions:
        target_version = str(next(iter(app_versions.values())))
    return {
        "lamdaState": str(health.get("lamda_state", health.get("state", "UNKNOWN"))),
        "edgeState": str(health.get("edge_state", "HEALTHY")),
        "targetAppVersion": str(health.get("target_app_version", target_version)),
        "batteryPercent": _safe_nonnegative_int(health.get("battery_percent")),
        "charging": bool(health.get("charging", False)),
        "network": str(health.get("network_type", "Offline")),
        "temperatureCelsius": health.get("temperature_celsius"),
        "freeStorageBytes": _safe_nonnegative_int(health.get("free_storage_bytes")),
        "companionVersion": str(health.get("companion_version", current_version)),
        "observedAt": str(observed_at),
        "automationStopped": bool(health.get("automation_stopped", False)),
    }


def _safe_nonnegative_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float) and value.is_integer():
        return max(0, int(value))
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return 0


def _task_snapshot(
    spool: EdgeSpool, device_id: str, active_command_id: str | None
) -> dict[str, object] | None:
    current = spool.command_for_device(device_id)
    if current is None:
        return None
    command, state = current
    state_map = {
        "RECEIVED": "QUEUED",
        "STARTED": "RUNNING",
        "SUCCEEDED": "SUCCEEDED",
        "FAILED": "FAILED",
        "CANCELED": "CANCELED",
        "BLOCKED_HARDWARE": "FAILED",
    }
    return {
        "taskRunId": command.task_run_id,
        "commandId": command.command_id,
        "state": state_map.get(state, "UNKNOWN"),
        "step": "runner",
        "cancellable": active_command_id == command.command_id,
        "confirmationId": None,
    }
