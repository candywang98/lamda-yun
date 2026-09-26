from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from cloudctl_edge_protocol import edge_control_pb2 as pb


class SpoolError(RuntimeError):
    pass


class StaleFencingToken(SpoolError):
    pass


@dataclass(frozen=True, slots=True)
class AcceptedCommand:
    inserted: bool
    state: str


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    command_id: str
    kind: str
    path: Path
    sha256: str
    size: int
    priority: int
    attempts: int


class EdgeSpool:
    """SQLite WAL spool. It is replay state, never a second business database."""

    def __init__(self, database: Path):
        database.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._create_schema()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def journal_mode(self) -> str:
        with self._lock:
            row = self._connection.execute("PRAGMA journal_mode").fetchone()
            return str(row[0]).lower()

    def accept_command(self, command: pb.StartCommand) -> AcceptedCommand:
        serialized = command.SerializeToString(deterministic=True)
        with self._transaction():
            existing = self._connection.execute(
                "SELECT serialized, state FROM commands WHERE command_id = ?", (command.command_id,)
            ).fetchone()
            if existing is not None:
                if bytes(existing["serialized"]) != serialized:
                    raise SpoolError("command_id was reused with different content")
                return AcceptedCommand(inserted=False, state=str(existing["state"]))

            fence = self._connection.execute(
                "SELECT fencing_token, lease_id FROM fence_tokens WHERE device_id = ?",
                (command.device_id,),
            ).fetchone()
            if fence is not None:
                current = int(fence["fencing_token"])
                lease_id = str(fence["lease_id"])
                if command.fencing_token < current:
                    raise StaleFencingToken(
                        f"fencing token {command.fencing_token} is below current token {current}"
                    )
                if command.fencing_token == current and command.lease_id != lease_id:
                    raise StaleFencingToken("current fencing token belongs to another lease")
            if fence is None or command.fencing_token > int(fence["fencing_token"]):
                self._connection.execute(
                    """
                    INSERT INTO fence_tokens(device_id, fencing_token, lease_id)
                    VALUES (?, ?, ?)
                    ON CONFLICT(device_id) DO UPDATE SET
                        fencing_token = excluded.fencing_token,
                        lease_id = excluded.lease_id
                    """,
                    (command.device_id, command.fencing_token, command.lease_id),
                )
            self._connection.execute(
                """
                INSERT INTO commands(
                    command_id, device_id, lease_id, fencing_token, command_type,
                    serialized, state, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'RECEIVED', ?)
                """,
                (
                    command.command_id,
                    command.device_id,
                    command.lease_id,
                    command.fencing_token,
                    command.command_type,
                    serialized,
                    datetime.now(UTC).isoformat(),
                ),
            )
            return AcceptedCommand(inserted=True, state="RECEIVED")

    def assert_current_fence(self, device_id: str, lease_id: str, fencing_token: int) -> None:
        with self._lock:
            row = self._connection.execute(
                "SELECT fencing_token, lease_id FROM fence_tokens WHERE device_id = ?", (device_id,)
            ).fetchone()
        if row is None or int(row["fencing_token"]) != fencing_token or row["lease_id"] != lease_id:
            raise StaleFencingToken("command no longer owns the current device fence")

    def command_state(self, command_id: str) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT state FROM commands WHERE command_id = ?", (command_id,)
            ).fetchone()
            return None if row is None else str(row["state"])

    def set_command_state(self, command_id: str, state: str) -> None:
        allowed = {
            "RECEIVED",
            "STARTED",
            "SUCCEEDED",
            "FAILED",
            "CANCELED",
            "BLOCKED_HARDWARE",
        }
        if state not in allowed:
            raise SpoolError(f"unsupported command state: {state}")
        with self._transaction():
            changed = self._connection.execute(
                "UPDATE commands SET state = ? WHERE command_id = ?", (state, command_id)
            ).rowcount
            if changed != 1:
                raise SpoolError("unknown command")

    def enqueue_edge_message(self, message: pb.EdgeToCloud, *, priority: int = 100) -> int:
        if message.WhichOneof("body") in {None, "hello"}:
            raise SpoolError("only sequenced Edge events may enter the spool")
        with self._transaction():
            sequence = self._metadata_int("last_edge_sequence") + 1
            stored = pb.EdgeToCloud()
            stored.CopyFrom(message)
            stored.sequence = sequence
            self._connection.execute(
                "INSERT INTO outbound(sequence, payload, priority, created_at) VALUES (?, ?, ?, ?)",
                (
                    sequence,
                    stored.SerializeToString(deterministic=True),
                    priority,
                    datetime.now(UTC).isoformat(),
                ),
            )
            self._set_metadata("last_edge_sequence", str(sequence))
            return sequence

    def record_cloud_with_edge_message(
        self,
        cloud_sequence: int,
        message: pb.EdgeToCloud,
        *,
        priority: int = 100,
    ) -> int:
        if message.WhichOneof("body") in {None, "hello"}:
            raise SpoolError("only sequenced Edge events may enter the spool")
        with self._transaction():
            current_cloud = self._metadata_int("last_cloud_sequence")
            if cloud_sequence != current_cloud + 1:
                raise SpoolError(
                    f"cloud sequence gap: expected {current_cloud + 1}, got {cloud_sequence}"
                )
            edge_sequence = self._metadata_int("last_edge_sequence") + 1
            stored = pb.EdgeToCloud()
            stored.CopyFrom(message)
            stored.sequence = edge_sequence
            self._connection.execute(
                "INSERT INTO outbound(sequence, payload, priority, created_at) VALUES (?, ?, ?, ?)",
                (
                    edge_sequence,
                    stored.SerializeToString(deterministic=True),
                    priority,
                    datetime.now(UTC).isoformat(),
                ),
            )
            self._set_metadata("last_edge_sequence", str(edge_sequence))
            self._set_metadata("last_cloud_sequence", str(cloud_sequence))
            return edge_sequence

    def replay_edge_messages(self, after_sequence: int = 0) -> list[pb.EdgeToCloud]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload FROM outbound WHERE sequence > ? AND acked = 0 ORDER BY sequence",
                (after_sequence,),
            ).fetchall()
        messages: list[pb.EdgeToCloud] = []
        for row in rows:
            message = pb.EdgeToCloud()
            message.ParseFromString(bytes(row["payload"]))
            messages.append(message)
        return messages

    def acknowledge_edge_sequence(self, through_sequence: int) -> None:
        with self._transaction():
            last_sequence = self._metadata_int("last_edge_sequence")
            if through_sequence > last_sequence:
                raise SpoolError("cloud acknowledged an Edge sequence that was never emitted")
            current_ack = self._metadata_int("last_edge_sequence_acked")
            if through_sequence <= current_ack:
                return
            self._connection.execute(
                "UPDATE outbound SET acked = 1 WHERE sequence <= ?", (through_sequence,)
            )
            self._set_metadata("last_edge_sequence_acked", str(through_sequence))

    def record_cloud_sequence(self, sequence: int) -> bool:
        if sequence < 1:
            raise SpoolError("cloud sequence must be positive")
        with self._transaction():
            current = self._metadata_int("last_cloud_sequence")
            if sequence <= current:
                return False
            if sequence != current + 1:
                raise SpoolError(f"cloud sequence gap: expected {current + 1}, got {sequence}")
            self._set_metadata("last_cloud_sequence", str(sequence))
            return True

    def put_debug_grant(self, grant: pb.DebugSessionGrant) -> None:
        payload = grant.SerializeToString(deterministic=True)
        with self._transaction():
            existing = self._connection.execute(
                "SELECT payload, revoked_at FROM debug_grants WHERE session_id = ?",
                (grant.session_id,),
            ).fetchone()
            if existing is not None:
                if bytes(existing["payload"]) != payload:
                    raise SpoolError("debug session ID was reused with different grant content")
                if existing["revoked_at"] is not None:
                    raise SpoolError("revoked debug session cannot be granted again")
                return
            self._connection.execute(
                "INSERT INTO debug_grants(session_id, payload, created_at) VALUES (?, ?, ?)",
                (grant.session_id, payload, datetime.now(UTC).isoformat()),
            )

    def revoke_debug_grant(self, session_id: str) -> None:
        with self._transaction():
            self._connection.execute(
                "UPDATE debug_grants SET revoked_at = COALESCE(revoked_at, ?) WHERE session_id = ?",
                (datetime.now(UTC).isoformat(), session_id),
            )

    def active_debug_grants(self) -> list[pb.DebugSessionGrant]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload FROM debug_grants WHERE revoked_at IS NULL ORDER BY created_at"
            ).fetchall()
        grants: list[pb.DebugSessionGrant] = []
        for row in rows:
            grant = pb.DebugSessionGrant()
            grant.ParseFromString(bytes(row["payload"]))
            grants.append(grant)
        return grants

    def last_cloud_sequence(self) -> int:
        with self._lock:
            return self._metadata_int("last_cloud_sequence")

    def add_evidence(self, record: EvidenceRecord) -> None:
        with self._transaction():
            self._connection.execute(
                """
                INSERT INTO evidence(
                    evidence_id, command_id, kind, path, sha256, size, priority, state, attempts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                """,
                (
                    record.evidence_id,
                    record.command_id,
                    record.kind,
                    str(record.path),
                    record.sha256,
                    record.size,
                    record.priority,
                    record.attempts,
                ),
            )

    def pending_evidence(self, limit: int = 100) -> list[EvidenceRecord]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM evidence WHERE state IN ('PENDING', 'RETRY')
                ORDER BY priority ASC, rowid ASC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            EvidenceRecord(
                evidence_id=str(row["evidence_id"]),
                command_id=str(row["command_id"]),
                kind=str(row["kind"]),
                path=Path(str(row["path"])),
                sha256=str(row["sha256"]),
                size=int(row["size"]),
                priority=int(row["priority"]),
                attempts=int(row["attempts"]),
            )
            for row in rows
        ]

    def mark_evidence_uploaded(self, evidence_id: str) -> None:
        with self._transaction():
            self._connection.execute(
                "UPDATE evidence SET state = 'UPLOADED' WHERE evidence_id = ?", (evidence_id,)
            )

    def mark_evidence_retry(self, evidence_id: str) -> None:
        with self._transaction():
            self._connection.execute(
                """
                UPDATE evidence
                SET state = 'RETRY', attempts = attempts + 1
                WHERE evidence_id = ?
                """,
                (evidence_id,),
            )

    def put_device_health(self, device_id: str, health: dict[str, object]) -> None:
        with self._transaction():
            self._connection.execute(
                """
                INSERT INTO device_health(device_id, payload_json, observed_at)
                VALUES (?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    observed_at = excluded.observed_at
                """,
                (device_id, json.dumps(health, sort_keys=True), datetime.now(UTC).isoformat()),
            )

    def get_device_health(self, device_id: str) -> dict[str, object] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json, observed_at FROM device_health WHERE device_id = ?",
                (device_id,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(str(row["payload_json"]))
        if not isinstance(payload, dict):
            raise SpoolError("stored device health is not an object")
        payload.setdefault("observed_at", str(row["observed_at"]))
        return payload

    def command_for_device(self, device_id: str) -> tuple[pb.StartCommand, str] | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT serialized, state FROM commands
                WHERE device_id = ?
                ORDER BY rowid DESC LIMIT 1
                """,
                (device_id,),
            ).fetchone()
        if row is None:
            return None
        command = pb.StartCommand()
        command.ParseFromString(bytes(row["serialized"]))
        return command, str(row["state"])

    def issue_companion_enrollment(
        self,
        *,
        code_digest: str,
        device_id: str,
        tenant_name: str,
        site_name: str,
    ) -> None:
        with self._transaction():
            self._connection.execute(
                """
                INSERT OR IGNORE INTO companion_enrollment_codes(
                    code_digest, device_id, tenant_name, site_name, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    code_digest,
                    device_id,
                    tenant_name,
                    site_name,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def consume_companion_enrollment(
        self,
        *,
        code_digest: str,
        token_digest: str,
    ) -> dict[str, str] | None:
        with self._transaction():
            row = self._connection.execute(
                """
                SELECT device_id, tenant_name, site_name, consumed_at
                FROM companion_enrollment_codes WHERE code_digest = ?
                """,
                (code_digest,),
            ).fetchone()
            if row is None or row["consumed_at"] is not None:
                return None
            now = datetime.now(UTC).isoformat()
            self._connection.execute(
                "UPDATE companion_enrollment_codes SET consumed_at = ? WHERE code_digest = ?",
                (now, code_digest),
            )
            self._connection.execute(
                """
                INSERT INTO companion_bindings(token_digest, device_id, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    token_digest = excluded.token_digest,
                    created_at = excluded.created_at,
                    revoked_at = NULL
                """,
                (token_digest, str(row["device_id"]), now),
            )
            return {
                "device_id": str(row["device_id"]),
                "tenant_name": str(row["tenant_name"]),
                "site_name": str(row["site_name"]),
            }

    def companion_binding_device(self, token_digest: str) -> str | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT device_id FROM companion_bindings
                WHERE token_digest = ? AND revoked_at IS NULL
                """,
                (token_digest,),
            ).fetchone()
        return None if row is None else str(row["device_id"])

    def revoke_companion_binding(self, *, token_digest: str, device_id: str) -> bool:
        with self._transaction():
            changed = self._connection.execute(
                """
                UPDATE companion_bindings SET revoked_at = ?
                WHERE token_digest = ? AND device_id = ? AND revoked_at IS NULL
                """,
                (datetime.now(UTC).isoformat(), token_digest, device_id),
            ).rowcount
        return changed == 1

    def put_artifact_delivery(self, event: pb.ArtifactDeliveryEvent) -> None:
        artifact_id = event.artifact.sha256 or event.artifact.object_key
        with self._transaction():
            self._connection.execute(
                """
                INSERT INTO artifact_deliveries(
                    command_id, task_run_id, device_id, artifact_id, kind, state,
                    bytes_received, size_bytes, error_code, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(command_id, artifact_id) DO UPDATE SET
                    state = excluded.state,
                    bytes_received = excluded.bytes_received,
                    error_code = excluded.error_code,
                    observed_at = excluded.observed_at
                """,
                (
                    event.command_id,
                    event.task_run_id,
                    event.device_id,
                    artifact_id,
                    event.artifact.kind,
                    event.state,
                    event.bytes_received,
                    event.artifact.size,
                    event.error_code,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def artifact_deliveries(self, device_id: str) -> list[dict[str, object]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT artifact_id, kind, state, bytes_received, size_bytes, error_code
                FROM artifact_deliveries WHERE device_id = ?
                ORDER BY observed_at DESC, rowid DESC
                """,
                (device_id,),
            ).fetchall()
        return [
            {
                "artifactId": str(row["artifact_id"]),
                "kind": str(row["kind"]),
                "state": str(row["state"]),
                "bytesReceived": int(row["bytes_received"]),
                "sizeBytes": int(row["size_bytes"]),
                "progressPercent": (
                    100
                    if int(row["size_bytes"]) == 0 and row["state"] == "DELIVERED"
                    else (
                        0
                        if int(row["size_bytes"]) == 0
                        else min(100, int(row["bytes_received"]) * 100 // int(row["size_bytes"]))
                    )
                ),
                "errorCode": str(row["error_code"]) or None,
            }
            for row in rows
        ]

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS commands (
                command_id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                lease_id TEXT NOT NULL,
                fencing_token INTEGER NOT NULL,
                command_type TEXT NOT NULL,
                serialized BLOB NOT NULL,
                state TEXT NOT NULL,
                received_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fence_tokens (
                device_id TEXT PRIMARY KEY,
                fencing_token INTEGER NOT NULL,
                lease_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbound (
                sequence INTEGER PRIMARY KEY,
                payload BLOB NOT NULL,
                priority INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                acked INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS evidence (
                evidence_id TEXT PRIMARY KEY,
                command_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size INTEGER NOT NULL,
                priority INTEGER NOT NULL,
                state TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS device_health (
                device_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                observed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS companion_enrollment_codes (
                code_digest TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                tenant_name TEXT NOT NULL,
                site_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                consumed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS companion_bindings (
                token_digest TEXT PRIMARY KEY,
                device_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                revoked_at TEXT
            );
            CREATE TABLE IF NOT EXISTS artifact_deliveries (
                command_id TEXT NOT NULL,
                task_run_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                state TEXT NOT NULL,
                bytes_received INTEGER NOT NULL,
                size_bytes INTEGER NOT NULL,
                error_code TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                PRIMARY KEY(command_id, artifact_id)
            );
            CREATE TABLE IF NOT EXISTS debug_grants (
                session_id TEXT PRIMARY KEY,
                payload BLOB NOT NULL,
                created_at TEXT NOT NULL,
                revoked_at TEXT
            );
            """
        )
        for key in ("last_edge_sequence", "last_edge_sequence_acked", "last_cloud_sequence"):
            self._connection.execute(
                "INSERT OR IGNORE INTO metadata(key, value) VALUES (?, '0')", (key,)
            )

    def _metadata_int(self, key: str) -> int:
        row = self._connection.execute(
            "SELECT value FROM metadata WHERE key = ?", (key,)
        ).fetchone()
        return int(row["value"]) if row else 0

    def _set_metadata(self, key: str, value: str) -> None:
        self._connection.execute(
            """
            INSERT INTO metadata(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    def _transaction(self) -> _Transaction:
        return _Transaction(self._connection, self._lock)


class _Transaction:
    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock):
        self._connection = connection
        self._lock = lock

    def __enter__(self) -> None:
        self._lock.acquire()
        self._connection.execute("BEGIN IMMEDIATE")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            self._connection.execute("COMMIT" if exc_type is None else "ROLLBACK")
        finally:
            self._lock.release()
