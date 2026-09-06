"""Small durable SQLite implementation of ``DebugDeliveryStore``."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from .debug_delivery import DebugDeliveryRecord, DebugDeliveryStore
from .session import SessionError


class SqliteDebugDeliveryStore(DebugDeliveryStore):
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._lock = asyncio.Lock()
        parent = Path(self._path).parent
        if str(parent) not in {"", "."}:
            parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS debug_delivery (
                session_id TEXT PRIMARY KEY, edge_id TEXT NOT NULL, device_id TEXT NOT NULL,
                capabilities TEXT NOT NULL, expires_at TEXT NOT NULL, state TEXT NOT NULL,
                error_code TEXT, detail TEXT, cloud_sequence INTEGER, lease_id TEXT,
                fencing_token INTEGER, relay_token_digest TEXT)"""
            )

    async def create(self, record: DebugDeliveryRecord) -> None:
        async with self._lock:

            def write() -> None:
                with sqlite3.connect(self._path) as db:
                    existing = db.execute(
                        "SELECT * FROM debug_delivery WHERE session_id=?",
                        (record.session_id,),
                    ).fetchone()
                    if existing:
                        if self._record(existing) != record:
                            raise SessionError(
                                "debug session delivery already exists with different input"
                            )
                        return
                    db.execute(
                        "INSERT INTO debug_delivery VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            record.session_id,
                            record.edge_id,
                            record.device_id,
                            ",".join(record.capabilities),
                            record.expires_at.isoformat(),
                            record.state,
                            record.error_code,
                            record.detail,
                            record.cloud_sequence,
                            record.lease_id,
                            record.fencing_token,
                            record.relay_token_digest,
                        ),
                    )

            write()

    async def update(
        self,
        session_id: str,
        *,
        state: str,
        error_code: str | None = None,
        detail: str | None = None,
        cloud_sequence: int | None = None,
    ) -> DebugDeliveryRecord:
        async with self._lock:

            def read() -> tuple[object, ...] | None:
                with sqlite3.connect(self._path) as db:
                    return db.execute(
                        "SELECT * FROM debug_delivery WHERE session_id=?", (session_id,)
                    ).fetchone()

            row = read()
            current = self._record(row) if row is not None else None
            if current is None:
                raise SessionError(f"unknown debug session delivery {session_id}")
            updated = replace(
                current,
                state=state,
                error_code=error_code,
                detail=detail,
                cloud_sequence=cloud_sequence or current.cloud_sequence,
            )

            def write() -> None:
                with sqlite3.connect(self._path) as db:
                    db.execute(
                        "UPDATE debug_delivery SET state=?,error_code=?,detail=?,"
                        "cloud_sequence=? WHERE session_id=?",
                        (
                            updated.state,
                            updated.error_code,
                            updated.detail,
                            updated.cloud_sequence,
                            session_id,
                        ),
                    )

            write()
            return updated

    async def get(self, session_id: str) -> DebugDeliveryRecord | None:
        def read() -> tuple[object, ...] | None:
            with sqlite3.connect(self._path) as db:
                row = db.execute(
                    "SELECT * FROM debug_delivery WHERE session_id=?", (session_id,)
                ).fetchone()
                return row

        row = read()
        return self._record(row) if row is not None else None

    @staticmethod
    def _record(row: tuple[object, ...]) -> DebugDeliveryRecord:
        # SQLite returns primitive types; cast for type safety
        cloud_seq = row[8]
        fencing = row[10]
        return DebugDeliveryRecord(
            session_id=str(row[0]),
            edge_id=str(row[1]),
            device_id=str(row[2]),
            capabilities=tuple(str(row[3]).split(",")),
            expires_at=datetime.fromisoformat(str(row[4])).astimezone(UTC),
            state=str(row[5]),
            error_code=str(row[6]) if row[6] is not None else None,
            detail=str(row[7]) if row[7] is not None else None,
            cloud_sequence=(
                int(cloud_seq) if isinstance(cloud_seq, (int, str)) else None  # type: ignore[arg-type]
            )
            if cloud_seq is not None
            else None,
            lease_id=str(row[9]) if row[9] is not None else None,
            fencing_token=(
                int(fencing) if isinstance(fencing, (int, str)) else None  # type: ignore[arg-type]
            )
            if fencing is not None
            else None,
            relay_token_digest=str(row[11]) if row[11] is not None else None,
        )
