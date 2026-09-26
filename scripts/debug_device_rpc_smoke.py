from __future__ import annotations

import asyncio
import base64
import json
import os
import secrets
import ssl
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import grpc
import websockets.asyncio.client
from cloudctl_edge_protocol import edge_control_pb2 as pb
from cloudctl_edge_protocol import edge_control_pb2_grpc as pb_grpc
from google.protobuf.json_format import ParseDict
from google.protobuf.struct_pb2 import Struct

EDGE_ID = "edge-oneplus9r-lab"
DEVICE_ID = "oneplus9r-b0644fb5"
LEASE_ID = "oneplus9r-lab-debug"


def _wait_for_marker(path: Path) -> None:
    while not path.exists():
        time.sleep(0.2)


def _event(
    *,
    event_id: str,
    session_id: str,
    event_type: str,
    payload: dict[str, object],
) -> pb.DebugEventRequest:
    return pb.DebugEventRequest(
        event_id=event_id,
        tenant_id="lab-smoke-tenant",
        aggregate_id=session_id,
        event_type=event_type,
        payload=ParseDict(payload, Struct()),
    )


async def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: debug_device_rpc_smoke.py CLIENT_CERT CLIENT_KEY CA_CERT")
    certificate, private_key, ca_certificate = map(Path, sys.argv[1:4])
    credentials = grpc.ssl_channel_credentials(
        root_certificates=ca_certificate.read_bytes(),
        certificate_chain=certificate.read_bytes(),
        private_key=private_key.read_bytes(),
    )
    channel = grpc.aio.secure_channel(
        "127.0.0.1:7443",
        credentials,
        options=(("grpc.ssl_target_name_override", "43.133.243.154.sslip.io"),),
    )
    stub = pb_grpc.EdgeControlStub(channel)
    session_id = "device-smoke-" + uuid.uuid4().hex
    relay_token = secrets.token_urlsafe(48)
    granted = False
    try:
        expires_at = datetime.now(UTC) + timedelta(minutes=5)
        grant = await stub.DeliverDebugEvent(
            _event(
                event_id="evt-grant-" + session_id,
                session_id=session_id,
                event_type="debug.session.grant_requested",
                payload={
                    "sessionId": session_id,
                    "deviceId": DEVICE_ID,
                    "edgeId": EDGE_ID,
                    "leaseId": LEASE_ID,
                    "fencingToken": 1,
                    "capabilities": ["view.frame", "view.layout", "input.tap"],
                    "expiresAt": expires_at.isoformat(),
                    "relayToken": relay_token,
                },
            ),
            timeout=10,
        )
        if not grant.accepted:
            raise RuntimeError(grant.detail)
        granted = True

        restart_marker_value = os.getenv("CLOUDCTL_DEBUG_RESTART_MARKER")
        if restart_marker_value:
            restart_marker = Path(restart_marker_value)
            print(
                json.dumps(
                    {"stage": "grant-delivered", "sessionId": session_id},
                    separators=(",", ":"),
                ),
                flush=True,
            )
            await asyncio.to_thread(_wait_for_marker, restart_marker)

        ssl_context = ssl.create_default_context(cafile=str(ca_certificate))
        async with websockets.asyncio.client.connect(
            "wss://127.0.0.1:17444/debug",
            ssl=ssl_context,
            server_hostname="43.133.243.154.sslip.io",
            origin="http://127.0.0.1:5173",
        ) as websocket:
            await websocket.send(
                json.dumps({"type": "debug.auth", "sessionId": session_id, "token": relay_token})
            )
            ready = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
            if ready.get("type") != "ready":
                raise RuntimeError(f"unexpected WSS ready message: {ready}")

            await websocket.send(json.dumps({"type": "view.layout", "sessionId": session_id}))
            layout_accepted = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
            if layout_accepted.get("type") != "debug.accepted":
                raise RuntimeError(f"unexpected layout acceptance: {layout_accepted}")
            layout = json.loads(await asyncio.wait_for(websocket.recv(), timeout=20))
            if layout.get("type") != "layout" or not isinstance(layout.get("nodes"), list):
                raise RuntimeError(f"unexpected device layout: {layout}")
            if not layout["nodes"]:
                raise RuntimeError("device UI tree is empty")

            await websocket.send(json.dumps({"type": "view.frame", "sessionId": session_id}))
            frame_accepted = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
            if frame_accepted.get("type") != "debug.accepted":
                raise RuntimeError(f"unexpected frame acceptance: {frame_accepted}")
            frame = json.loads(await asyncio.wait_for(websocket.recv(), timeout=20))
            if frame.get("type") != "frame" or frame.get("mediaType") != "image/png":
                raise RuntimeError(f"unexpected device frame: {frame}")
            screenshot = base64.b64decode(str(frame.get("data", "")), validate=True)
            if not screenshot.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError("device frame is not a PNG screenshot")

            await websocket.send(
                json.dumps(
                    {
                        "type": "input.tap",
                        "sessionId": session_id,
                        "x": 10,
                        "y": 10,
                    }
                )
            )
            accepted = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
            if accepted.get("type") != "debug.accepted":
                raise RuntimeError(f"unexpected WSS command response: {accepted}")
            acknowledged = json.loads(await asyncio.wait_for(websocket.recv(), timeout=20))
            if acknowledged.get("type") != "debug.ack":
                raise RuntimeError(f"unexpected device response: {acknowledged}")
            if acknowledged.get("state") != "SUCCEEDED":
                raise RuntimeError(f"device operation did not succeed: {acknowledged}")
            if acknowledged.get("commandId") != accepted.get("commandId"):
                raise RuntimeError("device acknowledgement command binding mismatch")
            print(
                json.dumps(
                    {
                        "sessionId": session_id,
                        "deviceId": DEVICE_ID,
                        "edgeId": EDGE_ID,
                        "ready": ready["type"],
                        "accepted": accepted["type"],
                        "ack": acknowledged["type"],
                        "state": acknowledged["state"],
                        "layoutNodes": len(layout["nodes"]),
                        "screenshotBytes": len(screenshot),
                    },
                    separators=(",", ":"),
                )
            )
    finally:
        if granted:
            revoke = await stub.DeliverDebugEvent(
                _event(
                    event_id="evt-revoke-" + session_id,
                    session_id=session_id,
                    event_type="debug.session.revoked",
                    payload={
                        "sessionId": session_id,
                        "deviceId": DEVICE_ID,
                        "edgeId": EDGE_ID,
                        "leaseId": LEASE_ID,
                        "fencingToken": 1,
                        "reason": "device smoke cleanup",
                    },
                ),
                timeout=10,
            )
            if not revoke.accepted:
                raise RuntimeError(revoke.detail)
        await channel.close()


if __name__ == "__main__":
    asyncio.run(main())
