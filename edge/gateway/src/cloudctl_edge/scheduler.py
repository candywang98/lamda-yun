from __future__ import annotations

import re
from datetime import UTC, datetime

from cloudctl_edge_protocol import edge_control_pb2 as pb

from .runner import RunnerBusy, RunnerSupervisor
from .spool import EdgeSpool, SpoolError, StaleFencingToken


class CommandScheduler:
    ALLOWED_COMMAND_TYPES = frozenset(
        {
            "RUN_AUTOMATION",
            "INSTALL_APK",
            "PREFETCH_ARTIFACTS",
            "PUSH_MEDIA",
            "COLLECT_HEALTH",
            "STOP_AUTOMATION",
        }
    )
    ARTIFACT_KINDS = frozenset({"APK", "APK_SPLIT", "MEDIA", "AUTOMATION_PACKAGE"})
    ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

    def __init__(self, spool: EdgeSpool, supervisor: RunnerSupervisor):
        self._spool = spool
        self._supervisor = supervisor

    def receive(self, command: pb.StartCommand, *, now: datetime | None = None) -> pb.CommandAck:
        error = self._validate(command, now=now or datetime.now(UTC))
        if error is not None:
            return pb.CommandAck(
                command_id=command.command_id,
                state="REJECTED",
                error_code=error[0],
                detail=error[1],
            )
        try:
            accepted = self._spool.accept_command(command)
        except StaleFencingToken as exc:
            return pb.CommandAck(
                command_id=command.command_id,
                state="REJECTED",
                error_code="EDGE_STALE_FENCE",
                detail=str(exc),
            )
        except SpoolError as exc:
            return pb.CommandAck(
                command_id=command.command_id,
                state="REJECTED",
                error_code="EDGE_COMMAND_CONFLICT",
                detail=str(exc),
            )
        if accepted.inserted:
            self._supervisor.cancel_stale(command.device_id, command.fencing_token)
        return pb.CommandAck(command_id=command.command_id, state=accepted.state)

    async def dispatch(self, command: pb.StartCommand) -> pb.CommandAck:
        if self._spool.command_state(command.command_id) != "RECEIVED":
            return pb.CommandAck(
                command_id=command.command_id,
                state="REJECTED",
                error_code="EDGE_COMMAND_STATE",
                detail="command is not dispatchable",
            )
        try:
            await self._supervisor.start(command)
        except RunnerBusy as exc:
            return pb.CommandAck(
                command_id=command.command_id,
                state="REJECTED",
                error_code="EDGE_DEVICE_BUSY",
                detail=str(exc),
            )
        return pb.CommandAck(command_id=command.command_id, state="STARTED")

    async def cancel(self, command: pb.CancelCommand) -> bool:
        return await self._supervisor.cancel(command.command_id)

    @classmethod
    def _validate(cls, command: pb.StartCommand, *, now: datetime) -> tuple[str, str] | None:
        identifiers = (
            command.command_id,
            command.task_run_id,
            command.device_id,
            command.lease_id,
        )
        if not all(cls.ID_PATTERN.fullmatch(value) for value in identifiers):
            return "EDGE_INVALID_COMMAND", "command, task run and device identifiers are required"
        if command.fencing_token < 1 or command.fencing_token > 2**63 - 1:
            return "EDGE_INVALID_LEASE", "lease_id and positive fencing_token are required"
        if command.command_type not in cls.ALLOWED_COMMAND_TYPES:
            return "EDGE_CAPABILITY_DENIED", "command type is not on the Edge allowlist"
        artifact_error = cls._validate_artifacts(command)
        if artifact_error is not None:
            return artifact_error
        if not command.HasField("deadline"):
            return "EDGE_DEADLINE_REQUIRED", "command deadline is required"
        deadline = command.deadline.ToDatetime(tzinfo=UTC)
        if deadline <= now:
            return "EDGE_DEADLINE_EXPIRED", "command deadline has expired"
        return None

    @classmethod
    def _validate_artifacts(cls, command: pb.StartCommand) -> tuple[str, str] | None:
        requires_artifacts = command.command_type in {
            "INSTALL_APK",
            "PREFETCH_ARTIFACTS",
            "PUSH_MEDIA",
        }
        if requires_artifacts and not command.artifacts:
            return "EDGE_ARTIFACT_REQUIRED", "command requires at least one approved artifact"
        allowed_by_command = {
            "INSTALL_APK": {"APK", "APK_SPLIT"},
            "PUSH_MEDIA": {"MEDIA"},
            "PREFETCH_ARTIFACTS": cls.ARTIFACT_KINDS,
            "RUN_AUTOMATION": {"MEDIA", "AUTOMATION_PACKAGE"},
        }
        allowed_kinds = allowed_by_command.get(command.command_type, set())
        for artifact in command.artifacts:
            if artifact.kind not in cls.ARTIFACT_KINDS or artifact.kind not in allowed_kinds:
                return "EDGE_ARTIFACT_KIND_DENIED", "artifact kind is not allowed for command"
            digest = artifact.sha256.lower()
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                return "EDGE_ARTIFACT_INVALID", "artifact SHA256 is invalid"
            if artifact.size < 0 or not artifact.object_key:
                return "EDGE_ARTIFACT_INVALID", "artifact object key and size are required"
            key_parts = artifact.object_key.replace("\\", "/").split("/")
            if any(part in {"", ".", ".."} for part in key_parts):
                return "EDGE_ARTIFACT_INVALID", "artifact object key is not canonical"
            if artifact.file_name and (
                "/" in artifact.file_name
                or "\\" in artifact.file_name
                or artifact.file_name in {".", ".."}
            ):
                return "EDGE_ARTIFACT_INVALID", "artifact file name cannot contain a path"
        return None
