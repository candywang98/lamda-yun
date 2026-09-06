from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
for source in ("packages/edge-protocol/src", "edge/gateway/src"):
    sys.path.insert(0, str(ROOT / source))

from cloudctl_edge.adb_debug import AdbDebugError, RestrictedAdbDebugDriver
from cloudctl_edge_protocol import edge_control_pb2 as pb


@pytest.mark.asyncio
async def test_tap_uses_fixed_serial_and_closed_argv_template(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    async def runner(argv: object) -> bytes:
        calls.append(tuple(argv))  # type: ignore[arg-type]
        return b""

    driver = RestrictedAdbDebugDriver(tmp_path / "adb", device_id="phone", runner=runner)
    response = await driver.handle(
        pb.DebugRelayFrame(
            session_id="s1",
            device_id="phone",
            request_id="r1",
            kind="tap",
            capability="input.tap",
            payload=b'{"x":12,"y":34}',
        )
    )
    assert calls == [(str(tmp_path / "adb"), "-s", "b0644fb5", "shell", "input", "tap", "12", "34")]
    assert response.kind == "debug.ack"
    assert response.capability == "debug.ack"
    assert response.request_id == "r1"
    assert json.loads(response.payload) == {"state": "SUCCEEDED"}


@pytest.mark.asyncio
async def test_capture_operations_have_no_caller_controlled_arguments(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    async def runner(argv: object) -> bytes:
        calls.append(tuple(argv))  # type: ignore[arg-type]
        return (
            b"PNG"
            if "screencap" in calls[-1]
            else b'<?xml version="1.0"?><hierarchy><node text="Publish" '
            b'resource-id="com.example:id/publish" class="android.widget.Button" '
            b'clickable="true" bounds="[744,2210][1026,2320]" /></hierarchy>'
            b"\r\nUI hierchary dumped to: /dev/tty\r\n"
        )

    driver = RestrictedAdbDebugDriver(tmp_path / "adb", device_id="phone", runner=runner)
    responses = []
    for kind, capability in (("frame", "view.frame"), ("layout", "view.layout")):
        responses.append(
            await driver.handle(
                pb.DebugRelayFrame(
                    device_id="phone", kind=kind, capability=capability, payload=b"{}"
                )
            )
        )
    assert calls[0][-3:] == ("exec-out", "screencap", "-p")
    assert calls[1][-4:] == ("exec-out", "uiautomator", "dump", "/dev/tty")
    assert [(item.kind, item.capability) for item in responses] == [
        ("frame", "view.frame"),
        ("layout", "view.layout"),
    ]
    assert json.loads(responses[1].payload)["nodes"] == [
        {
            "id": "com.example:id/publish",
            "className": "android.widget.Button",
            "bounds": "[744,2210][1026,2320]",
            "depth": 0,
            "clickable": True,
            "centerX": 885,
            "centerY": 2265,
            "resourceId": "com.example:id/publish",
            "text": "Publish",
        }
    ]


@pytest.mark.asyncio
async def test_arbitrary_payload_and_operation_are_rejected(tmp_path: Path) -> None:
    async def runner(_argv: object) -> bytes:
        raise AssertionError("process must not start")

    driver = RestrictedAdbDebugDriver(tmp_path / "adb", device_id="phone", runner=runner)
    with pytest.raises(AdbDebugError, match="only integer x and y"):
        await driver.handle(
            pb.DebugRelayFrame(
                kind="tap",
                device_id="phone",
                capability="input.tap",
                payload=b'{"x":1,"y":2,"shell":"id"}',
            )
        )
    with pytest.raises(AdbDebugError, match="not allowlisted"):
        await driver.handle(
            pb.DebugRelayFrame(
                kind="shell",
                device_id="phone",
                capability="shell",
                payload=b'{"command":"id"}',
            )
        )


@pytest.mark.asyncio
async def test_frame_cannot_target_another_device(tmp_path: Path) -> None:
    async def runner(_argv: object) -> bytes:
        raise AssertionError("process must not start")

    driver = RestrictedAdbDebugDriver(tmp_path / "adb", device_id="phone-a", runner=runner)
    with pytest.raises(AdbDebugError, match="configured lab device"):
        await driver.handle(
            pb.DebugRelayFrame(
                device_id="phone-b",
                kind="tap",
                capability="input.tap",
                payload=b'{"x":1,"y":2}',
            )
        )
