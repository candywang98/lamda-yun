from __future__ import annotations

import asyncio
import json
import secrets
import ssl
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import grpc
import websockets.asyncio.client
from cloudctl_edge_protocol import edge_control_pb2 as pb
from cloudctl_edge_protocol import edge_control_pb2_grpc as pb_grpc
from google.protobuf.json_format import ParseDict
from google.protobuf.struct_pb2 import Struct


async def main() -> None:
    certificate, private_key, ca_certificate = map(Path, sys.argv[1:4])
    credentials = grpc.ssl_channel_credentials(
        root_certificates=ca_certificate.read_bytes(),
        certificate_chain=certificate.read_bytes(),
        private_key=private_key.read_bytes(),
    )
    channel = grpc.aio.secure_channel(
        "127.0.0.1:7443",
        credentials,
        options=(("grpc.ssl_target_name_override", "43.133.243.154"),),
    )
    session_id = "remote-smoke-" + uuid.uuid4().hex
    try:
        stub = pb_grpc.EdgeControlStub(channel)
        expires_at = datetime.now(UTC) + timedelta(minutes=5)
        relay_token = secrets.token_urlsafe(48)
        response = await stub.DeliverDebugEvent(
            pb.DebugEventRequest(
                event_id="evt-grant-" + session_id,
                tenant_id="smoke-tenant",
                aggregate_id=session_id,
                event_type="debug.session.grant_requested",
                payload=ParseDict(
                    {
                        "sessionId": session_id,
                        "deviceId": "smoke-device",
                        "edgeId": "smoke-edge",
                        "leaseId": "smoke-lease",
                        "fencingToken": 1,
                        "capabilities": ["input.tap", "view.frame"],
                        "expiresAt": expires_at.isoformat(),
                        "relayToken": relay_token,
                    },
                    Struct(),
                ),
            ),
            timeout=10,
        )
        if not response.accepted:
            raise RuntimeError(response.detail)
        ssl_context = ssl.create_default_context(cafile=str(ca_certificate))
        async with websockets.asyncio.client.connect(
            "wss://127.0.0.1:17444/debug",
            ssl=ssl_context,
            server_hostname="43.133.243.154",
            origin="http://127.0.0.1:5173",
        ) as websocket:
            await websocket.send(
                json.dumps({"type": "debug.auth", "sessionId": session_id, "token": relay_token})
            )
            ready = json.loads(await websocket.recv())
            if ready.get("type") != "ready":
                raise RuntimeError(f"unexpected WSS ready message: {ready}")
            await websocket.send(
                json.dumps(
                    {
                        "type": "input.tap",
                        "sessionId": session_id,
                        "x": 10,
                        "y": 20,
                    }
                )
            )
            accepted = json.loads(await websocket.recv())
            if accepted.get("type") != "debug.accepted":
                raise RuntimeError(f"unexpected WSS command response: {accepted}")
        response = await stub.DeliverDebugEvent(
            pb.DebugEventRequest(
                event_id="evt-revoke-" + session_id,
                tenant_id="smoke-tenant",
                aggregate_id=session_id,
                event_type="debug.session.revoked",
                payload=ParseDict(
                    {
                        "sessionId": session_id,
                        "deviceId": "smoke-device",
                        "edgeId": "smoke-edge",
                        "leaseId": "smoke-lease",
                        "fencingToken": 1,
                        "reason": "local server smoke cleanup",
                    },
                    Struct(),
                ),
            ),
            timeout=10,
        )
        print(response.accepted, response.detail, ready["type"], accepted["type"], session_id)
    finally:
        await channel.close()


if __name__ == "__main__":
    asyncio.run(main())
