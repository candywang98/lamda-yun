from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).parents[1]
for source in ("packages/edge-protocol/src", "packages/lamda-driver/src", "edge/gateway/src"):
    sys.path.insert(0, str(ROOT / source))

from cloudctl_edge.companion_contract import (
    ArtifactDeliveryState,
    ArtifactDeliveryStatus,
    ArtifactKind,
    AuthorizedTaskState,
    AuthorizedTaskStatus,
    CompanionSnapshot,
    ConfirmationPrompt,
    ConfirmationRiskLevel,
    OperatorActionType,
    PublicDeviceHealth,
)
from cloudctl_edge.device_registry import DeviceRegistry
from cloudctl_edge.mock_device import MockDevice
from cloudctl_edge.operator_actions import OperatorActionCoordinator, OperatorActionError
from cloudctl_edge.runner import RunnerSupervisor
from cloudctl_edge.scheduler import CommandScheduler
from cloudctl_edge.spool import EdgeSpool
from cloudctl_edge_protocol import edge_control_pb2 as pb


class CancelAwareExecutor:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def execute(self, command, cancel_event, event_sink) -> None:
        self.started.set()
        await cancel_event.wait()


async def no_op_sink(event: pb.TaskEvent) -> None:
    return None


def command(command_id: str = "cmd-1") -> pb.StartCommand:
    value = pb.StartCommand(
        command_id=command_id,
        task_run_id="task-1",
        device_id="device-1",
        lease_id="lease-1",
        fencing_token=1,
        command_type="COLLECT_HEALTH",
    )
    value.deadline.FromDatetime(datetime.now(UTC) + timedelta(minutes=1))
    return value


def confirmation() -> pb.ConfirmationRequired:
    value = pb.ConfirmationRequired(
        confirmation_id="confirm-1",
        command_id="cmd-1",
        task_run_id="task-1",
        device_id="device-1",
        title="Approve authorized publish",
        detail="The final publish step needs an operator decision.",
        risk_level="HIGH",
    )
    value.expires_at.FromDatetime(datetime.now(UTC) + timedelta(minutes=5))
    return value


def test_device_heartbeat_contains_console_health_and_task_fields(tmp_path: Path) -> None:
    spool = EdgeSpool(tmp_path / "spool.sqlite3")
    registry = DeviceRegistry("edge-1", spool)
    registry.register(
        MockDevice(
            device_id="device-1",
            battery_percent=37,
            charging=False,
            network_type="ETHERNET",
            temperature_celsius=41.25,
            free_storage_bytes=123456,
            companion_version="1.2.3",
            current_task_run_id="task-1",
            current_task_state="RUNNING",
            stopped=True,
        )
    )

    device = registry.heartbeat().devices[0]
    assert device.battery_percent == 37
    assert device.charging is False
    assert device.network_type == "ETHERNET"
    assert device.temperature_celsius == pytest.approx(41.25)
    assert device.free_storage_bytes == 123456
    assert device.companion_version == "1.2.3"
    assert device.current_task_run_id == "task-1"
    assert device.current_task_state == "RUNNING"
    assert device.automation_stopped is True


def test_companion_snapshot_serializes_typed_task_delivery_and_risk() -> None:
    observed_at = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    snapshot = CompanionSnapshot(
        health=PublicDeviceHealth(
            lamda_state="HEALTHY",
            edge_state="HEALTHY",
            target_app_version="4.5.6",
            battery_percent=88,
            charging=True,
            network="WIFI",
            temperature_celsius=34.5,
            free_storage_bytes=4096,
            companion_version="1.2.3",
            observed_at=observed_at,
        ),
        task=AuthorizedTaskStatus(
            task_run_id="task-1",
            command_id="cmd-1",
            state=AuthorizedTaskState.WAITING_CONFIRMATION,
            step="publish",
            cancellable=True,
            confirmation_id="confirm-1",
        ),
        confirmation=ConfirmationPrompt(
            confirmation_id="confirm-1",
            title="Confirm publish",
            detail="Review the authorized target before publishing.",
            risk_level=ConfirmationRiskLevel.HIGH,
            expires_at=observed_at + timedelta(minutes=5),
        ),
        deliveries=(
            ArtifactDeliveryStatus(
                artifact_id="apk-1",
                kind=ArtifactKind.APK,
                state=ArtifactDeliveryState.DOWNLOADING,
                bytes_received=25,
                size_bytes=100,
            ),
        ),
        automation_stopped=False,
    ).to_wire()

    assert snapshot["health"]["companionVersion"] == "1.2.3"
    assert snapshot["task"] == {
        "taskRunId": "task-1",
        "commandId": "cmd-1",
        "state": "WAITING_CONFIRMATION",
        "step": "publish",
        "cancellable": True,
        "confirmationId": "confirm-1",
    }
    assert snapshot["confirmation"]["riskLevel"] == "HIGH"
    assert snapshot["deliveries"][0]["progressPercent"] == 25
    assert snapshot["currentTask"] == "task-1"
    assert snapshot["automationStopped"] is False


@pytest.mark.asyncio
async def test_operator_actions_are_allowlisted_durable_and_cloud_resolved(tmp_path: Path) -> None:
    spool = EdgeSpool(tmp_path / "spool.sqlite3")
    executor = CancelAwareExecutor()
    supervisor = RunnerSupervisor(spool, executor, no_op_sink)
    scheduler = CommandScheduler(spool, supervisor)
    active = command()
    assert scheduler.receive(active).state == "RECEIVED"
    assert (await scheduler.dispatch(active)).state == "STARTED"
    await executor.started.wait()

    coordinator = OperatorActionCoordinator(spool, supervisor)
    coordinator.require_confirmation(confirmation())
    visible = coordinator.active_confirmation("device-1")
    assert visible is not None
    visible.title = "mutated caller copy"
    assert coordinator.active_confirmation("device-1").title == "Approve authorized publish"

    recorded = await coordinator.record_local_action(
        action=OperatorActionType.CONFIRM,
        device_id="device-1",
        command_id="cmd-1",
        confirmation_id="confirm-1",
    )
    assert recorded.action == "CONFIRM"
    coordinator.resolve_from_cloud(
        pb.ConfirmationResolution(
            confirmation_id="confirm-1",
            command_id="cmd-1",
            approved=True,
            actor_id="operator-1",
        )
    )
    assert await coordinator.wait_for_resolution("confirm-1") is True

    stopped = await coordinator.record_local_action(
        action=OperatorActionType.STOP_AUTOMATION,
        device_id="device-1",
        command_id="cmd-1",
    )
    await supervisor.wait("device-1")
    assert stopped.action == "STOP_AUTOMATION"
    assert spool.command_state("cmd-1") == "CANCELED"
    assert [message.WhichOneof("body") for message in spool.replay_edge_messages()] == [
        "confirmation_required",
        "operator_action",
        "operator_action",
    ]

    with pytest.raises(OperatorActionError, match="allowlist"):
        await coordinator.record_local_action(
            action=cast(OperatorActionType, "SHELL"),
            device_id="device-1",
            command_id="cmd-1",
        )
