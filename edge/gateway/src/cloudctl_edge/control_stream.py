from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC

import grpc
from cloudctl_edge_protocol import edge_control_pb2 as pb
from cloudctl_edge_protocol import edge_control_pb2_grpc as pb_grpc

from .cert_store import EdgeCredentials
from .operator_actions import OperatorActionCoordinator
from .remote_proxy import DebugSessionError, DebugSessionManager, ProxyTarget
from .scheduler import CommandScheduler
from .settings import validate_hub_tls_server_name
from .spool import EdgeSpool


class ControlStreamError(RuntimeError):
    pass


class EdgeControlStream:
    def __init__(
        self,
        *,
        edge_id: str,
        software_version: str,
        spool: EdgeSpool,
        scheduler: CommandScheduler,
        debug_sessions: DebugSessionManager | None = None,
        debug_target_resolver: Callable[[str], ProxyTarget] | None = None,
        debug_frame_handler: Callable[[pb.DebugRelayFrame], Awaitable[None]] | None = None,
        edge_certificate_fingerprint: str | None = None,
        operator_actions: OperatorActionCoordinator | None = None,
    ):
        self._edge_id = edge_id
        self._software_version = software_version
        self._spool = spool
        self._scheduler = scheduler
        self._debug_sessions = debug_sessions
        self._debug_target_resolver = debug_target_resolver
        self._debug_frame_handler = debug_frame_handler
        self._edge_certificate_fingerprint = edge_certificate_fingerprint
        self._operator_actions = operator_actions
        self._wake = asyncio.Event()

    def notify_outbound(self) -> None:
        self._wake.set()

    async def run_once(self, stub: pb_grpc.EdgeControlStub) -> None:
        call = stub.Connect(self._outbound())
        async for message in call:
            await self.handle_cloud(message)

    async def run_forever(
        self,
        *,
        endpoint: str,
        credentials: EdgeCredentials,
        stop_event: asyncio.Event,
        tls_server_name: str | None = None,
    ) -> None:
        delay_seconds = 1
        while not stop_event.is_set():
            channel = secure_channel(endpoint, credentials, tls_server_name=tls_server_name)
            try:
                await self.run_once(pb_grpc.EdgeControlStub(channel))
                delay_seconds = 1
            except ControlStreamError:
                raise
            except grpc.aio.AioRpcError:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=delay_seconds)
                except TimeoutError:
                    delay_seconds = min(delay_seconds * 2, 30)
            finally:
                await channel.close()

    async def handle_cloud(self, message: pb.CloudToEdge) -> None:
        body = message.WhichOneof("body")
        if body == "hello":
            if message.sequence != 0:
                raise ControlStreamError("Cloud hello must have sequence zero")
            self._spool.acknowledge_edge_sequence(message.hello.last_edge_sequence_acked)
            return
        if body is None:
            raise ControlStreamError("cloud message body is required")
        current_sequence = self._spool.last_cloud_sequence()
        if message.sequence <= current_sequence:
            return
        if message.sequence != current_sequence + 1:
            raise ControlStreamError(
                f"cloud sequence gap: expected {current_sequence + 1}, got {message.sequence}"
            )
        if body == "start":
            received = self._scheduler.receive(message.start)
            self._enqueue_ack(received, cloud_sequence=message.sequence)
            if received.state == "RECEIVED":
                started = await self._scheduler.dispatch(message.start)
                self._enqueue_ack(started)
        elif body == "cancel":
            canceled = await self._scheduler.cancel(message.cancel)
            ack = pb.CommandAck(
                command_id=message.cancel.command_id,
                state="STARTED" if canceled else "REJECTED",
                error_code="" if canceled else "EDGE_COMMAND_NOT_ACTIVE",
            )
            self._enqueue_ack(ack, cloud_sequence=message.sequence)
        elif body == "debug_grant":
            if self._debug_sessions is None or self._debug_target_resolver is None:
                raise ControlStreamError("debug proxy is not configured on this Edge")
            grant = message.debug_grant
            if not grant.relay_token or len(grant.relay_token) < 32:
                raise ControlStreamError("debug grant relay token is missing or too short")
            if not grant.lease_id or grant.fencing_token < 1:
                raise ControlStreamError("debug grant lease fence is missing")
            self._debug_sessions.grant(
                session_id=grant.session_id,
                device_id=grant.device_id,
                expires_at=grant.expires_at.ToDatetime(tzinfo=UTC),
                capabilities=set(grant.capabilities),
                target=self._debug_target_resolver(grant.device_id),
                bearer_token=grant.relay_token,
                lease_id=grant.lease_id,
                fencing_token=grant.fencing_token,
            )
            self._spool.put_debug_grant(grant)
            self._spool.record_cloud_sequence(message.sequence)
        elif body == "revocations":
            fingerprint = (self._edge_certificate_fingerprint or "").lower()
            if fingerprint and fingerprint in {
                value.lower() for value in message.revocations.revoked_fingerprints
            }:
                raise ControlStreamError("Edge certificate was revoked")
            self._spool.record_cloud_sequence(message.sequence)
        elif body == "confirmation_resolution":
            if self._operator_actions is None:
                raise ControlStreamError("operator action coordination is not configured")
            self._operator_actions.resolve_from_cloud(message.confirmation_resolution)
            self._spool.record_cloud_sequence(message.sequence)
        elif body == "debug_revoke":
            if self._debug_sessions is None:
                raise ControlStreamError("debug proxy is not configured on this Edge")
            revoke = message.debug_revoke
            if not revoke.session_id:
                raise ControlStreamError("debug revoke session id is required")
            self._debug_sessions.revoke(revoke.session_id)
            self._spool.revoke_debug_grant(revoke.session_id)
            self._spool.record_cloud_sequence(message.sequence)
        elif body == "relay_frame":
            if self._debug_sessions is None:
                raise ControlStreamError("debug proxy is not configured on this Edge")
            frame = message.relay_frame
            if not frame.device_id:
                raise ControlStreamError("debug relay frame device binding is required")
            try:
                self._debug_sessions.validate_frame(frame, device_id=frame.device_id)
            except DebugSessionError:
                await self.emit_debug_frame(
                    pb.DebugRelayFrame(
                        session_id=frame.session_id,
                        device_id=frame.device_id,
                        request_id=frame.request_id,
                        capability="debug.ack",
                        kind="debug.ack",
                        payload=json.dumps(
                            {"state": "FAILED", "errorCode": "DEBUG_SESSION_NOT_ACTIVE"},
                            separators=(",", ":"),
                        ).encode("utf-8"),
                        end=True,
                    )
                )
                self._spool.record_cloud_sequence(message.sequence)
                return
            if self._debug_frame_handler is None:
                raise ControlStreamError("debug relay frame handler is not configured")
            await self._debug_frame_handler(frame)
            self._spool.record_cloud_sequence(message.sequence)

    async def _outbound(self) -> AsyncIterator[pb.EdgeToCloud]:
        yield pb.EdgeToCloud(
            sequence=0,
            hello=pb.EdgeHello(
                edge_id=self._edge_id,
                software_version=self._software_version,
                last_cloud_sequence_acked=self._spool.last_cloud_sequence(),
            ),
        )
        last_sent = 0
        while True:
            for message in self._spool.replay_edge_messages(after_sequence=last_sent):
                last_sent = message.sequence
                yield message
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=10)
            except TimeoutError:
                continue

    def _enqueue_ack(self, ack: pb.CommandAck, *, cloud_sequence: int | None = None) -> None:
        message = pb.EdgeToCloud(command_ack=ack)
        if cloud_sequence is None:
            self._spool.enqueue_edge_message(message, priority=0)
        else:
            self._spool.record_cloud_with_edge_message(cloud_sequence, message, priority=0)
        self.notify_outbound()

    async def emit_task_event(self, event: pb.TaskEvent) -> None:
        self._spool.enqueue_edge_message(pb.EdgeToCloud(task_event=event), priority=10)
        self.notify_outbound()

    async def emit_debug_frame(self, frame: pb.DebugRelayFrame) -> None:
        """Send a bounded device response back through the outbound tunnel."""
        if not frame.session_id or not frame.device_id:
            raise ControlStreamError("debug response session and device binding are required")
        if len(frame.payload) > 256 * 1024:
            raise ControlStreamError("debug response payload exceeds limit")
        self._spool.enqueue_edge_message(pb.EdgeToCloud(relay_frame=frame), priority=0)
        self.notify_outbound()

    def emit_heartbeat(self, heartbeat: pb.Heartbeat) -> None:
        self._spool.enqueue_edge_message(pb.EdgeToCloud(heartbeat=heartbeat), priority=20)
        self.notify_outbound()


def secure_channel(
    endpoint: str,
    credentials: EdgeCredentials,
    *,
    tls_server_name: str | None = None,
) -> grpc.aio.Channel:
    if "://" in endpoint and not endpoint.startswith("https://"):
        raise ControlStreamError("Edge Hub endpoint must use HTTPS/TLS semantics")
    if endpoint.endswith(":65000"):
        raise ControlStreamError("Edge Hub must use TLS and cannot be a device service endpoint")
    if not all((credentials.certificate, credentials.private_key, credentials.certificate_chain)):
        raise ControlStreamError("complete Edge mTLS credentials are required")
    channel_credentials = grpc.ssl_channel_credentials(
        root_certificates=credentials.certificate_chain,
        private_key=credentials.private_key,
        certificate_chain=credentials.certificate,
    )
    options: tuple[tuple[str, str], ...] = ()
    if tls_server_name is not None:
        validate_hub_tls_server_name(tls_server_name)
        options = (("grpc.ssl_target_name_override", tls_server_name),)
    return grpc.aio.secure_channel(
        endpoint.removeprefix("https://"), channel_credentials, options=options
    )
