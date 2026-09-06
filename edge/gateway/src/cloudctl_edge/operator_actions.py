from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, datetime

from cloudctl_edge_protocol import edge_control_pb2 as pb

from .companion_contract import OperatorActionType
from .runner import RunnerSupervisor
from .spool import EdgeSpool


class OperatorActionError(ValueError):
    pass


class OperatorActionCoordinator:
    """Bridges visible Companion actions to durable Edge events and runner control."""

    _ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    _RISK_LEVELS = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})

    def __init__(self, spool: EdgeSpool, supervisor: RunnerSupervisor):
        self._spool = spool
        self._supervisor = supervisor
        self._confirmations: dict[str, pb.ConfirmationRequired] = {}
        self._resolutions: dict[str, asyncio.Future[bool]] = {}
        self._resolved: dict[str, bool] = {}

    def require_confirmation(self, required: pb.ConfirmationRequired) -> None:
        if not all(
            (
                required.confirmation_id,
                required.command_id,
                required.task_run_id,
                required.device_id,
                required.title,
            )
        ):
            raise OperatorActionError("confirmation identifiers and title are required")
        expires_at = required.expires_at.ToDatetime(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise OperatorActionError("confirmation already expired")
        if required.risk_level not in self._RISK_LEVELS:
            raise OperatorActionError("confirmation risk level is invalid")
        existing = self._confirmations.get(required.confirmation_id)
        if existing is not None:
            if existing.SerializeToString(deterministic=True) != required.SerializeToString(
                deterministic=True
            ):
                raise OperatorActionError("confirmation identifier was reused")
            return
        copied = pb.ConfirmationRequired()
        copied.CopyFrom(required)
        self._confirmations[required.confirmation_id] = copied
        self._spool.enqueue_edge_message(pb.EdgeToCloud(confirmation_required=copied), priority=0)

    async def record_local_action(
        self,
        *,
        action: OperatorActionType,
        device_id: str,
        command_id: str,
        confirmation_id: str = "",
    ) -> pb.OperatorAction:
        if not isinstance(action, OperatorActionType):
            raise OperatorActionError("operator action is not on the local allowlist")
        if not self._ID_PATTERN.fullmatch(device_id) or not self._ID_PATTERN.fullmatch(command_id):
            raise OperatorActionError("device and command identifiers are invalid")
        if action in {OperatorActionType.CONFIRM, OperatorActionType.REJECT}:
            if not self._ID_PATTERN.fullmatch(confirmation_id):
                raise OperatorActionError("confirmation identifier is invalid")
            required = self._confirmations.get(confirmation_id)
            if (
                required is None
                or required.command_id != command_id
                or required.device_id != device_id
            ):
                raise OperatorActionError("confirmation is not active for this command")
            if required.expires_at.ToDatetime(tzinfo=UTC) <= datetime.now(UTC):
                self._discard_confirmation(confirmation_id)
                raise OperatorActionError("confirmation expired")
        elif confirmation_id:
            raise OperatorActionError("stop action cannot carry a confirmation identifier")
        if action == OperatorActionType.STOP_AUTOMATION:
            await self._supervisor.cancel(command_id)
        recorded = pb.OperatorAction(
            action_id=str(uuid.uuid4()),
            device_id=device_id,
            command_id=command_id,
            confirmation_id=confirmation_id,
            action=action.value,
        )
        recorded.occurred_at.FromDatetime(datetime.now(UTC))
        self._spool.enqueue_edge_message(pb.EdgeToCloud(operator_action=recorded), priority=0)
        return recorded

    def resolve_from_cloud(self, resolution: pb.ConfirmationResolution) -> None:
        required = self._confirmations.get(resolution.confirmation_id)
        if required is None or required.command_id != resolution.command_id:
            raise OperatorActionError("confirmation resolution does not match an active request")
        if required.expires_at.ToDatetime(tzinfo=UTC) <= datetime.now(UTC):
            self._discard_confirmation(resolution.confirmation_id)
            raise OperatorActionError("confirmation expired")
        future = self._resolutions.get(resolution.confirmation_id)
        if future is None:
            self._resolved[resolution.confirmation_id] = resolution.approved
        elif not future.done():
            future.set_result(resolution.approved)

    async def wait_for_resolution(self, confirmation_id: str) -> bool:
        if confirmation_id not in self._confirmations:
            raise OperatorActionError("confirmation is not active")
        if confirmation_id in self._resolved:
            resolved = self._resolved.pop(confirmation_id)
            self._confirmations.pop(confirmation_id, None)
            return resolved
        future = self._resolutions.setdefault(
            confirmation_id, asyncio.get_running_loop().create_future()
        )
        try:
            return await future
        finally:
            self._discard_confirmation(confirmation_id)

    def active_confirmation(self, device_id: str) -> pb.ConfirmationRequired | None:
        now = datetime.now(UTC)
        for confirmation_id, required in tuple(self._confirmations.items()):
            if required.expires_at.ToDatetime(tzinfo=UTC) <= now:
                self._discard_confirmation(confirmation_id)
                continue
            if required.device_id == device_id:
                copied = pb.ConfirmationRequired()
                copied.CopyFrom(required)
                return copied
        return None

    def _discard_confirmation(self, confirmation_id: str) -> None:
        future = self._resolutions.pop(confirmation_id, None)
        if future is not None and not future.done():
            future.cancel()
        self._resolved.pop(confirmation_id, None)
        self._confirmations.pop(confirmation_id, None)
