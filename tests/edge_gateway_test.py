from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
for source in ("packages/edge-protocol/src", "edge/gateway/src"):
    sys.path.insert(0, str(ROOT / source))

from cloudctl_edge.remote_proxy import DebugSessionError, DebugSessionManager, ProxyTarget
from cloudctl_edge.runner import RunnerSupervisor
from cloudctl_edge.scheduler import CommandScheduler
from cloudctl_edge.spool import EdgeSpool
from cloudctl_edge_protocol import edge_control_pb2 as pb


def start(command_id: str, device_id: str = "device-a", token: int = 1) -> pb.StartCommand:
    value = pb.StartCommand(
        command_id=command_id,
        task_run_id=f"task-{command_id}",
        device_id=device_id,
        lease_id=f"lease-{token}",
        fencing_token=token,
        command_type="COLLECT_HEALTH",
    )
    value.deadline.FromDatetime(datetime.now(UTC) + timedelta(minutes=1))
    return value


class BlockingExecutor:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(self, command, cancel_event, event_sink) -> None:
        self.started.set()
        await self.release.wait()


@pytest.mark.asyncio
async def test_supervisor_allows_one_runner_per_device(tmp_path: Path) -> None:
    spool = EdgeSpool(tmp_path / "spool.sqlite3")
    events: list[pb.TaskEvent] = []

    async def sink(event: pb.TaskEvent) -> None:
        events.append(event)

    executor = BlockingExecutor()
    supervisor = RunnerSupervisor(spool, executor, sink)
    scheduler = CommandScheduler(spool, supervisor)
    first = start("one")
    second = start("two", token=2)
    assert scheduler.receive(first).state == "RECEIVED"
    assert (await scheduler.dispatch(first)).state == "STARTED"
    await executor.started.wait()
    assert scheduler.receive(second).state == "RECEIVED"
    rejected = await scheduler.dispatch(second)
    assert rejected.error_code == "EDGE_DEVICE_BUSY"
    executor.release.set()
    await supervisor.wait("device-a")
    assert spool.command_state("one") == "CANCELED"
    assert [event.state for event in events] == ["STARTED", "CANCELED"]
    assert (await scheduler.dispatch(second)).state == "STARTED"
    await supervisor.wait("device-a")
    assert spool.command_state("two") == "SUCCEEDED"


def test_scheduler_denies_arbitrary_command(tmp_path: Path) -> None:
    spool = EdgeSpool(tmp_path / "spool.sqlite3")

    async def sink(event: pb.TaskEvent) -> None:
        return None

    scheduler = CommandScheduler(spool, RunnerSupervisor(spool, BlockingExecutor(), sink))
    value = start("unsafe")
    value.command_type = "SHELL"
    rejection = scheduler.receive(value)
    assert rejection.state == "REJECTED"
    assert rejection.error_code == "EDGE_CAPABILITY_DENIED"


def test_scheduler_accepts_typed_apk_and_media_artifacts(tmp_path: Path) -> None:
    spool = EdgeSpool(tmp_path / "spool.sqlite3")

    async def sink(event: pb.TaskEvent) -> None:
        return None

    scheduler = CommandScheduler(spool, RunnerSupervisor(spool, BlockingExecutor(), sink))
    apk = start("apk")
    apk.command_type = "INSTALL_APK"
    apk.artifacts.add(
        object_key="approved/apk/client.apk",
        sha256="a" * 64,
        size=4096,
        kind="APK",
        content_type="application/vnd.android.package-archive",
        file_name="client.apk",
        package_name="com.example.client",
    )
    assert scheduler.receive(apk).state == "RECEIVED"

    media = start("media")
    media.command_type = "PUSH_MEDIA"
    media.artifacts.add(
        object_key="approved/media/banner.png",
        sha256="b" * 64,
        size=2048,
        kind="MEDIA",
        content_type="image/png",
        file_name="banner.png",
    )
    assert scheduler.receive(media).state == "RECEIVED"


@pytest.mark.parametrize(
    ("command_type", "kind", "object_key", "digest", "error_code"),
    [
        ("INSTALL_APK", "MEDIA", "approved/app.apk", "a" * 64, "EDGE_ARTIFACT_KIND_DENIED"),
        ("PUSH_MEDIA", "MEDIA", "../private/photo.png", "b" * 64, "EDGE_ARTIFACT_INVALID"),
        ("INSTALL_APK", "APK", "approved/app.apk", "not-a-hash", "EDGE_ARTIFACT_INVALID"),
    ],
)
def test_scheduler_rejects_mismatched_or_unsafe_artifacts(
    tmp_path: Path,
    command_type: str,
    kind: str,
    object_key: str,
    digest: str,
    error_code: str,
) -> None:
    spool = EdgeSpool(tmp_path / command_type / "spool.sqlite3")

    async def sink(event: pb.TaskEvent) -> None:
        return None

    scheduler = CommandScheduler(spool, RunnerSupervisor(spool, BlockingExecutor(), sink))
    value = start("artifact")
    value.command_type = command_type
    value.artifacts.add(
        object_key=object_key,
        sha256=digest,
        size=128,
        kind=kind,
        file_name="payload.bin",
    )
    rejection = scheduler.receive(value)
    assert rejection.state == "REJECTED"
    assert rejection.error_code == error_code


def test_debug_session_is_short_lived_scoped_and_private() -> None:
    manager = DebugSessionManager()
    now = datetime(2026, 8, 30, tzinfo=UTC)
    token = manager.grant(
        session_id="session-a",
        device_id="device-a",
        expires_at=now + timedelta(minutes=5),
        capabilities={"view"},
        target=ProxyTarget("10.0.0.20"),
        now=now,
    )
    target = manager.authorize(
        session_id="session-a",
        device_id="device-a",
        token=token,
        capability="view",
        now=now + timedelta(minutes=1),
    )
    assert target.port == 65000
    with pytest.raises(DebugSessionError):
        manager.authorize(
            session_id="session-a",
            device_id="device-a",
            token=token,
            capability="input",
            now=now,
        )
    with pytest.raises(DebugSessionError):
        manager.grant(
            session_id="session-b",
            device_id="device-a",
            expires_at=now + timedelta(minutes=5),
            capabilities={"shell"},
            target=ProxyTarget("10.0.0.20"),
            now=now,
        )
