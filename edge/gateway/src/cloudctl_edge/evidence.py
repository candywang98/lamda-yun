from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import uuid
from pathlib import Path
from typing import BinaryIO, Protocol

from cloudctl_edge_protocol import edge_control_pb2 as pb

from .spool import EdgeSpool, EvidenceRecord


class EvidenceUploader(Protocol):
    async def upload(self, record: EvidenceRecord) -> None: ...


class EvidenceQueue:
    PRIORITY = {"commit": 0, "result": 10, "ui_xml": 30, "log": 50, "screenshot": 60}

    def __init__(self, root: Path, spool: EdgeSpool):
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._spool = spool

    def capture(self, *, command_id: str, kind: str, source: BinaryIO) -> EvidenceRecord:
        evidence_id = str(uuid.uuid4())
        command_directory = hashlib.sha256(command_id.encode("utf-8")).hexdigest()
        target = self._root / command_directory / evidence_id
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix="evidence-", dir=target.parent)
        digest = hashlib.sha256()
        size = 0
        try:
            with os.fdopen(descriptor, "wb") as destination:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, target)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        record = EvidenceRecord(
            evidence_id=evidence_id,
            command_id=command_id,
            kind=kind,
            path=target,
            sha256=digest.hexdigest(),
            size=size,
            priority=self.PRIORITY.get(kind, 100),
            attempts=0,
        )
        self._spool.add_evidence(record)
        self._spool.enqueue_edge_message(
            pb.EdgeToCloud(
                evidence_ready=pb.EvidenceReady(
                    command_id=command_id,
                    evidence_id=evidence_id,
                    kind=kind,
                    sha256=record.sha256,
                    size=size,
                )
            ),
            priority=record.priority,
        )
        return record

    async def flush(self, uploader: EvidenceUploader, *, limit: int = 100) -> int:
        uploaded = 0
        for record in self._spool.pending_evidence(limit):
            valid = await asyncio.to_thread(self._is_valid, record)
            if not valid:
                self._spool.mark_evidence_retry(record.evidence_id)
                continue
            try:
                await uploader.upload(record)
            except Exception:
                self._spool.mark_evidence_retry(record.evidence_id)
                continue
            self._spool.mark_evidence_uploaded(record.evidence_id)
            uploaded += 1
        return uploaded

    @classmethod
    def _is_valid(cls, record: EvidenceRecord) -> bool:
        return record.path.is_file() and cls._hash(record.path) == record.sha256

    @staticmethod
    def _hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
