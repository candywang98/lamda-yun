from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cloudctl_edge.control_stream import EdgeControlStream
from cloudctl_edge.remote_proxy import DebugSessionManager, ProxyTarget
from cloudctl_edge.runner import RunnerSupervisor
from cloudctl_edge.scheduler import CommandScheduler
from cloudctl_edge.spool import EdgeSpool
from cloudctl_edge_protocol import edge_control_pb2 as pb


class _UnusedExecutor:
    async def execute(self, command, cancel_event, event_sink) -> None:
        raise AssertionError("debug relay must not enter the arbitrary command scheduler")


@pytest.mark.asyncio
async def test_debug_frame_adapter_is_session_bound_and_can_emit_ack(tmp_path: Path) -> None:
    spool = EdgeSpool(tmp_path / "edge.sqlite3")

    async def task_sink(event: pb.TaskEvent) -> None:
        raise AssertionError("debug relay must not emit task events")

    scheduler = CommandScheduler(spool, RunnerSupervisor(spool, _UnusedExecutor(), task_sink))
    sessions = DebugSessionManager()
    now = datetime.now(UTC)
    sessions.grant(
        session_id="debug-a",
        device_id="device-a",
        expires_at=now + timedelta(minutes=5),
        capabilities={"input.tap"},
        target=ProxyTarget("127.0.0.1"),
        bearer_token="x" * 48,
        lease_id="lease-a",
        fencing_token=9,
        now=now,
    )
    control: EdgeControlStream

    async def device_adapter(frame: pb.DebugRelayFrame) -> None:
        await control.emit_debug_frame(
            pb.DebugRelayFrame(
                session_id=frame.session_id,
                device_id=frame.device_id,
                request_id=frame.request_id,
                capability="input.tap",
                kind="ack",
                payload=b'{"state":"ACCEPTED"}',
                end=True,
            )
        )

    control = EdgeControlStream(
        edge_id="edge-a",
        software_version="test",
        spool=spool,
        scheduler=scheduler,
        debug_sessions=sessions,
        debug_frame_handler=device_adapter,
    )
    await control.handle_cloud(
        pb.CloudToEdge(
            sequence=1,
            relay_frame=pb.DebugRelayFrame(
                session_id="debug-a",
                device_id="device-a",
                request_id="request-a",
                capability="input.tap",
                kind="tap",
                payload=b'{"locator":"approved.button"}',
            ),
        )
    )
    outbound = spool.replay_edge_messages(after_sequence=0)
    assert len(outbound) == 1
    assert outbound[0].WhichOneof("body") == "relay_frame"
    assert outbound[0].relay_frame.kind == "ack"
    assert outbound[0].relay_frame.request_id == "request-a"
    assert spool.last_cloud_sequence() == 1


@pytest.mark.asyncio
async def test_debug_frame_without_active_session_emits_failed_ack_and_advances_sequence(
    tmp_path: Path,
) -> None:
    spool = EdgeSpool(tmp_path / "edge.sqlite3")

    async def task_sink(event: pb.TaskEvent) -> None:
        raise AssertionError("debug relay must not emit task events")

    scheduler = CommandScheduler(spool, RunnerSupervisor(spool, _UnusedExecutor(), task_sink))

    async def device_adapter(frame: pb.DebugRelayFrame) -> None:
        raise AssertionError("inactive debug session must not reach the device adapter")

    control = EdgeControlStream(
        edge_id="edge-a",
        software_version="test",
        spool=spool,
        scheduler=scheduler,
        debug_sessions=DebugSessionManager(),
        debug_frame_handler=device_adapter,
    )

    await control.handle_cloud(
        pb.CloudToEdge(
            sequence=1,
            relay_frame=pb.DebugRelayFrame(
                session_id="missing-session",
                device_id="device-a",
                request_id="request-missing",
                capability="input.tap",
                kind="tap",
                payload=b'{"x":1,"y":2}',
            ),
        )
    )

    outbound = spool.replay_edge_messages(after_sequence=0)
    assert len(outbound) == 1
    assert outbound[0].sequence == 1
    assert outbound[0].WhichOneof("body") == "relay_frame"
    failed = outbound[0].relay_frame
    assert failed.session_id == "missing-session"
    assert failed.device_id == "device-a"
    assert failed.request_id == "request-missing"
    assert failed.capability == "debug.ack"
    assert failed.kind == "debug.ack"
    assert failed.end is True
    assert json.loads(failed.payload) == {
        "state": "FAILED",
        "errorCode": "DEBUG_SESSION_NOT_ACTIVE",
    }
    assert spool.last_cloud_sequence() == 1
