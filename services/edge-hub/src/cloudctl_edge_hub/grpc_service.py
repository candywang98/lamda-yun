from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

import grpc
from cloudctl_edge_protocol import edge_control_pb2 as pb
from cloudctl_edge_protocol import edge_control_pb2_grpc as pb_grpc
from google.protobuf.json_format import MessageToDict

from .identity import IdentityError, PeerIdentityVerifier
from .session import EdgeHub, SessionError


class EdgeControlService(pb_grpc.EdgeControlServicer):
    def __init__(
        self,
        hub: EdgeHub,
        identity_verifier: PeerIdentityVerifier,
        debug_event_handler: Callable[[dict[str, object]], Awaitable[None]] | None = None,
    ) -> None:
        self._hub = hub
        self._identity_verifier = identity_verifier
        self._debug_event_handler = debug_event_handler

    async def DeliverDebugEvent(
        self, request: pb.DebugEventRequest, context: grpc.aio.ServicerContext
    ) -> pb.DebugEventResponse:
        try:
            self._identity_verifier.verify_control_plane(context.auth_context())
        except IdentityError as exc:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, str(exc))
        handler = self._debug_event_handler
        if handler is None:
            await context.abort(grpc.StatusCode.UNIMPLEMENTED, "debug event delivery is disabled")
            return pb.DebugEventResponse(accepted=False, detail="debug event delivery is disabled")
        if not request.event_id or not request.aggregate_id or not request.event_type:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "event identity is required")
        if request.event_type not in {"debug.session.grant_requested", "debug.session.revoked"}:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "event type is not allowed")
        payload = MessageToDict(request.payload, preserving_proto_field_name=False)
        event: dict[str, object] = {
            "eventId": request.event_id,
            "tenantId": request.tenant_id,
            "aggregateId": request.aggregate_id,
            "eventType": request.event_type,
            "payload": payload,
        }
        try:
            await handler(event)
        except SessionError as exc:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(exc))
        return pb.DebugEventResponse(accepted=True, detail="debug event accepted")

    async def Connect(
        self,
        request_iterator: AsyncIterator[pb.EdgeToCloud],
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[pb.CloudToEdge]:
        try:
            first = await anext(request_iterator)
        except StopAsyncIteration:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Edge hello is required")
            return
        if first.WhichOneof("body") != "hello" or first.sequence != 0:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT, "first message must be sequence-zero hello"
            )
            return
        hello = first.hello
        try:
            self._identity_verifier.verify(context.auth_context(), hello.edge_id)
        except IdentityError as exc:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, str(exc))
            return

        receive_task = asyncio.create_task(self._receive(hello.edge_id, request_iterator, context))
        try:
            async for outbound in self._hub.open(hello.edge_id, hello.last_cloud_sequence_acked):
                if receive_task.done():
                    await receive_task
                    return
                yield outbound
        finally:
            receive_task.cancel()
            await asyncio.gather(receive_task, return_exceptions=True)

    async def _receive(
        self,
        edge_id: str,
        request_iterator: AsyncIterator[pb.EdgeToCloud],
        context: grpc.aio.ServicerContext,
    ) -> None:
        try:
            async for incoming in request_iterator:
                await self._hub.accept(edge_id, incoming)
        except SessionError as exc:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(exc))
