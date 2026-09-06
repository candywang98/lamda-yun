"""Durable SQLite-backed Edge Hub stream state."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import stat
from collections import defaultdict
from pathlib import Path

from cloudctl_edge_protocol import edge_control_pb2 as pb

from .session import SessionError


class SqliteHubStore:
    """Persist stream sequences and unacknowledged cloud messages across restarts."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        if not self._path.is_absolute():
            raise SessionError("Edge Hub state database path must be absolute")
        state_directory = self._path.parent
        state_directory_created = not state_directory.exists()
        state_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if state_directory_created:
            os.chmod(state_directory, 0o700)
        elif stat.S_IMODE(state_directory.stat().st_mode) & 0o077:
            raise SessionError(
                "Edge Hub state database directory must not grant group or other access"
            )
        self._lock = asyncio.Lock()
        self._subscribers: defaultdict[str, set[asyncio.Queue[pb.CloudToEdge]]] = defaultdict(set)
        try:
            with self._connect() as db:
                db.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS hub_edge_state (
                        edge_id TEXT PRIMARY KEY,
                        last_cloud_sequence INTEGER NOT NULL DEFAULT 0,
                        cloud_ack_watermark INTEGER NOT NULL DEFAULT 0,
                        last_edge_sequence INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE TABLE IF NOT EXISTS hub_cloud_message (
                        edge_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        payload BLOB NOT NULL,
                        PRIMARY KEY(edge_id, sequence)
                    );
                    CREATE TABLE IF NOT EXISTS hub_edge_message (
                        edge_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        payload BLOB NOT NULL,
                        PRIMARY KEY(edge_id, sequence)
                    );
                    """
                )
            os.chmod(self._path, 0o600)
        except (OSError, sqlite3.Error) as exc:
            raise SessionError(f"cannot initialize Edge Hub state database: {exc}") from exc

    async def append_cloud(self, edge_id: str, message: pb.CloudToEdge) -> pb.CloudToEdge:
        async with self._lock:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                state = self._state(db, edge_id)
                sequence = int(state[0]) + 1
                stored = pb.CloudToEdge()
                stored.CopyFrom(message)
                stored.sequence = sequence
                db.execute(
                    "INSERT INTO hub_cloud_message(edge_id, sequence, payload) VALUES (?, ?, ?)",
                    (edge_id, sequence, stored.SerializeToString()),
                )
                db.execute(
                    "UPDATE hub_edge_state SET last_cloud_sequence=? WHERE edge_id=?",
                    (sequence, edge_id),
                )
                db.commit()
            for queue in tuple(self._subscribers[edge_id]):
                queue.put_nowait(stored)
            return stored

    async def acknowledge_cloud(self, edge_id: str, through_sequence: int) -> None:
        if through_sequence < 0:
            raise SessionError("Edge cloud acknowledgement cannot be negative")
        async with self._lock:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                last_cloud, watermark, _last_edge = self._state(db, edge_id)
                if through_sequence < int(watermark):
                    raise SessionError("Edge cloud acknowledgement moved behind durable watermark")
                if through_sequence > int(last_cloud):
                    if int(last_cloud) != 0 or int(watermark) != 0:
                        raise SessionError(
                            "Edge acknowledged a cloud sequence that was never emitted"
                        )
                    db.execute(
                        "UPDATE hub_edge_state "
                        "SET last_cloud_sequence=?, cloud_ack_watermark=? WHERE edge_id=?",
                        (through_sequence, through_sequence, edge_id),
                    )
                    db.commit()
                    return
                db.execute(
                    "UPDATE hub_edge_state SET cloud_ack_watermark=? WHERE edge_id=?",
                    (through_sequence, edge_id),
                )
                db.execute(
                    "DELETE FROM hub_cloud_message WHERE edge_id=? AND sequence<=?",
                    (edge_id, through_sequence),
                )
                db.commit()

    async def replay_cloud(self, edge_id: str, after_sequence: int) -> list[pb.CloudToEdge]:
        async with self._lock:
            with self._connect() as db:
                rows = db.execute(
                    "SELECT payload FROM hub_cloud_message "
                    "WHERE edge_id=? AND sequence>? ORDER BY sequence",
                    (edge_id, after_sequence),
                ).fetchall()
        return [self._cloud_message(bytes(row[0])) for row in rows]

    async def record_edge(self, edge_id: str, message: pb.EdgeToCloud) -> bool:
        if message.sequence < 1:
            raise SessionError("Edge sequence must be positive")
        payload = message.SerializeToString()
        async with self._lock:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                _last_cloud, _watermark, last_edge = self._state(db, edge_id)
                existing = db.execute(
                    "SELECT payload FROM hub_edge_message WHERE edge_id=? AND sequence=?",
                    (edge_id, message.sequence),
                ).fetchone()
                if existing is not None:
                    if bytes(existing[0]) != payload:
                        raise SessionError("same Edge sequence was reused with different content")
                    db.rollback()
                    return False
                expected = int(last_edge) + 1
                if message.sequence != expected:
                    raise SessionError(
                        f"Edge sequence gap: expected {expected}, got {message.sequence}"
                    )
                db.execute(
                    "INSERT INTO hub_edge_message(edge_id, sequence, payload) VALUES (?, ?, ?)",
                    (edge_id, message.sequence, payload),
                )
                db.execute(
                    "UPDATE hub_edge_state SET last_edge_sequence=? WHERE edge_id=?",
                    (message.sequence, edge_id),
                )
                db.commit()
                return True

    async def last_edge_sequence(self, edge_id: str) -> int:
        async with self._lock:
            with self._connect() as db:
                return int(self._state(db, edge_id)[2])

    async def last_cloud_sequence(self, edge_id: str) -> int:
        async with self._lock:
            with self._connect() as db:
                return int(self._state(db, edge_id)[0])

    def live_queue(self, edge_id: str) -> asyncio.Queue[pb.CloudToEdge]:
        queue: asyncio.Queue[pb.CloudToEdge] = asyncio.Queue()
        self._subscribers[edge_id].add(queue)
        return queue

    def remove_live_queue(self, edge_id: str, queue: asyncio.Queue[pb.CloudToEdge]) -> None:
        self._subscribers[edge_id].discard(queue)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self._path, timeout=30)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    @staticmethod
    def _state(db: sqlite3.Connection, edge_id: str) -> tuple[int, int, int]:
        db.execute(
            "INSERT OR IGNORE INTO hub_edge_state(edge_id) VALUES (?)",
            (edge_id,),
        )
        row = db.execute(
            "SELECT last_cloud_sequence, cloud_ack_watermark, last_edge_sequence "
            "FROM hub_edge_state WHERE edge_id=?",
            (edge_id,),
        ).fetchone()
        if row is None:  # pragma: no cover - protected by INSERT OR IGNORE
            raise SessionError("could not initialize Edge Hub stream state")
        return int(row[0]), int(row[1]), int(row[2])

    @staticmethod
    def _cloud_message(payload: bytes) -> pb.CloudToEdge:
        message = pb.CloudToEdge()
        message.ParseFromString(payload)
        return message
