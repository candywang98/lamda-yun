from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from cloudctl_edge_protocol import edge_control_pb2 as pb


class SessionError(ValueError):
    pass


class HubStore(Protocol):
    async def append_cloud(self, edge_id: str, message: pb.CloudToEdge) -> pb.CloudToEdge: ...
    async def acknowledge_cloud(self, edge_id: str, through_sequence: int) -> None: ...
    async def replay_cloud(self, edge_id: str, after_sequence: int) -> list[pb.CloudToEdge]: ...
    async def record_edge(self, edge_id: str, message: pb.EdgeToCloud) -> bool: ...
    async def last_edge_sequence(self, edge_id: str) -> int: ...
    async def last_cloud_sequence(self, edge_id: str) -> int: ...
    def live_queue(self, edge_id: str) -> asyncio.Queue[pb.CloudToEdge]: ...
    def remove_live_queue(self, edge_id: str, queue: asyncio.Queue[pb.CloudToEdge]) -> None: ...


EdgeMessageHandler = Callable[[str, pb.EdgeToCloud], Awaitable[None]]


@dataclass(slots=True)
class _EdgeState:
    cloud_messages: list[pb.CloudToEdge] = field(default_factory=list)
    edge_messages: dict[int, pb.EdgeToCloud] = field(default_factory=dict)
    last_cloud_sequence: int = 0
    cloud_ack_watermark: int = 0
    subscribers: set[asyncio.Queue[pb.CloudToEdge]] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class InMemoryHubStore:
    """Test/store adapter; production can replace it with the PostgreSQL implementation."""

    def __init__(self) -> None:
        self._states: defaultdict[str, _EdgeState] = defaultdict(_EdgeState)

    async def append_cloud(self, edge_id: str, message: pb.CloudToEdge) -> pb.CloudToEdge:
        state = self._states[edge_id]
        async with state.lock:
            stored = pb.CloudToEdge()
            stored.CopyFrom(message)
            state.last_cloud_sequence += 1
            stored.sequence = state.last_cloud_sequence
            state.cloud_messages.append(stored)
            for queue in state.subscribers:
                await queue.put(stored)
            return stored

    async def acknowledge_cloud(self, edge_id: str, through_sequence: int) -> None:
        state = self._states[edge_id]
        async with state.lock:
            if through_sequence < state.cloud_ack_watermark:
                raise SessionError("Edge cloud acknowledgement moved behind durable watermark")
            if through_sequence > state.last_cloud_sequence:
                raise SessionError("Edge acknowledged a cloud sequence that was never emitted")
            state.cloud_ack_watermark = through_sequence
            state.cloud_messages = [
                message for message in state.cloud_messages if message.sequence > through_sequence
            ]

    async def replay_cloud(self, edge_id: str, after_sequence: int) -> list[pb.CloudToEdge]:
        state = self._states[edge_id]
        async with state.lock:
            return [
                message for message in state.cloud_messages if message.sequence > after_sequence
            ]

    async def record_edge(self, edge_id: str, message: pb.EdgeToCloud) -> bool:
        if message.sequence < 1:
            raise SessionError("Edge sequence must be positive")
        state = self._states[edge_id]
        async with state.lock:
            existing = state.edge_messages.get(message.sequence)
            if existing is not None:
                if existing.SerializeToString() != message.SerializeToString():
                    raise SessionError("same Edge sequence was reused with different content")
                return False
            expected = len(state.edge_messages) + 1
            if message.sequence != expected:
                raise SessionError(
                    f"Edge sequence gap: expected {expected}, got {message.sequence}"
                )
            copied = pb.EdgeToCloud()
            copied.CopyFrom(message)
            state.edge_messages[message.sequence] = copied
            return True

    async def last_edge_sequence(self, edge_id: str) -> int:
        state = self._states[edge_id]
        async with state.lock:
            return len(state.edge_messages)

    async def last_cloud_sequence(self, edge_id: str) -> int:
        state = self._states[edge_id]
        async with state.lock:
            return state.last_cloud_sequence

    def live_queue(self, edge_id: str) -> asyncio.Queue[pb.CloudToEdge]:
        queue: asyncio.Queue[pb.CloudToEdge] = asyncio.Queue()
        self._states[edge_id].subscribers.add(queue)
        return queue

    def remove_live_queue(self, edge_id: str, queue: asyncio.Queue[pb.CloudToEdge]) -> None:
        self._states[edge_id].subscribers.discard(queue)


class EdgeHub:
    def __init__(self, store: HubStore):
        self._store = store
        self._handlers: list[EdgeMessageHandler] = []

    def on_edge_message(self, handler: EdgeMessageHandler) -> None:
        self._handlers.append(handler)

    async def queue(self, edge_id: str, message: pb.CloudToEdge) -> pb.CloudToEdge:
        if not edge_id:
            raise SessionError("edge_id is required")
        if message.WhichOneof("body") is None:
            raise SessionError("cloud message body is required")
        return await self._store.append_cloud(edge_id, message)

    async def accept(self, edge_id: str, message: pb.EdgeToCloud) -> bool:
        if message.WhichOneof("body") == "hello":
            raise SessionError("Edge hello is session metadata, not a sequenced event")
        inserted = await self._store.record_edge(edge_id, message)
        if inserted:
            for handler in self._handlers:
                await handler(edge_id, message)
        return inserted

    async def open(
        self, edge_id: str, last_cloud_sequence_acked: int
    ) -> AsyncIterator[pb.CloudToEdge]:
        queue = self._store.live_queue(edge_id)
        try:
            await self._store.acknowledge_cloud(edge_id, last_cloud_sequence_acked)
            last_edge = await self._store.last_edge_sequence(edge_id)
            yield pb.CloudToEdge(
                sequence=0,
                hello=pb.CloudHello(last_edge_sequence_acked=last_edge),
            )
            cursor = last_cloud_sequence_acked
            for message in await self._store.replay_cloud(edge_id, cursor):
                cursor = message.sequence
                yield message
            while True:
                message = await queue.get()
                if message.sequence > cursor:
                    cursor = message.sequence
                    yield message
        finally:
            self._store.remove_live_queue(edge_id, queue)
