from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import BinaryIO


class ArtifactError(ValueError):
    pass


class ArtifactCache:
    def __init__(self, root: Path, *, max_bytes: int = 10 * 1024 * 1024 * 1024):
        self._root = root
        self._objects = root / "objects"
        self._objects.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_bytes
        self._lock = threading.RLock()
        self._index = sqlite3.connect(
            root / "index.sqlite3", check_same_thread=False, isolation_level=None
        )
        self._index.row_factory = sqlite3.Row
        self._index.execute("PRAGMA journal_mode=WAL")
        self._index.execute(
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                sha256 TEXT PRIMARY KEY,
                size INTEGER NOT NULL,
                path TEXT NOT NULL,
                last_access REAL NOT NULL
            )
            """
        )

    @property
    def objects_root(self) -> Path:
        return self._objects

    def close(self) -> None:
        with self._lock:
            self._index.close()

    def put(self, source: BinaryIO, *, expected_sha256: str, expected_size: int) -> Path:
        digest_name = self._validate_digest(expected_sha256)
        if expected_size < 0:
            raise ArtifactError("artifact size cannot be negative")
        if expected_size > self._max_bytes:
            raise ArtifactError("artifact is larger than the entire Edge cache budget")
        target = self._objects / digest_name[:2] / digest_name
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix="artifact-", dir=target.parent)
        actual_size = 0
        digest = hashlib.sha256()
        try:
            with os.fdopen(descriptor, "wb") as destination:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                    actual_size += len(chunk)
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            if actual_size != expected_size:
                raise ArtifactError(
                    f"artifact size mismatch: expected {expected_size}, got {actual_size}"
                )
            if digest.hexdigest() != digest_name:
                raise ArtifactError("artifact SHA256 mismatch")
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, target)
            with self._lock:
                self._index.execute(
                    """
                    INSERT INTO artifacts(sha256, size, path, last_access) VALUES (?, ?, ?, ?)
                    ON CONFLICT(sha256) DO UPDATE SET
                        size = excluded.size,
                        path = excluded.path,
                        last_access = excluded.last_access
                    """,
                    (digest_name, actual_size, str(target), time.time()),
                )
                self._prune_locked(exclude={digest_name})
            return target
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def get(self, sha256: str) -> Path:
        digest_name = self._validate_digest(sha256)
        with self._lock:
            row = self._index.execute(
                "SELECT path, size FROM artifacts WHERE sha256 = ?", (digest_name,)
            ).fetchone()
        if row is None:
            raise FileNotFoundError(digest_name)
        path = Path(str(row["path"]))
        if not path.is_file() or self._hash(path) != digest_name:
            with self._lock:
                self._index.execute("DELETE FROM artifacts WHERE sha256 = ?", (digest_name,))
            raise ArtifactError("cached artifact is missing or corrupted")
        with self._lock:
            self._index.execute(
                "UPDATE artifacts SET last_access = ? WHERE sha256 = ?", (time.time(), digest_name)
            )
        return path

    def _prune_locked(self, *, exclude: set[str]) -> None:
        rows = self._index.execute(
            "SELECT sha256, size, path FROM artifacts ORDER BY last_access DESC"
        ).fetchall()
        total = sum(int(row["size"]) for row in rows)
        for row in reversed(rows):
            digest_name = str(row["sha256"])
            if total <= self._max_bytes or digest_name in exclude:
                continue
            path = Path(str(row["path"]))
            try:
                path.unlink(missing_ok=True)
            finally:
                self._index.execute("DELETE FROM artifacts WHERE sha256 = ?", (digest_name,))
                total -= int(row["size"])

    @staticmethod
    def _validate_digest(value: str) -> str:
        normalized = value.lower()
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ArtifactError("SHA256 must be 64 hexadecimal characters")
        return normalized

    @staticmethod
    def _hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
