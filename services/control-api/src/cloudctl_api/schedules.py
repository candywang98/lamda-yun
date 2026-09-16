"""Appointment and recurring schedules that mint independent PlatformTasks."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cloudctl_domain import Actor, ConflictError, NotFoundError, Permission, ValidationError, require_permissions
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .command_v1 import CommandType
from .db import AccountDeviceBindingRow, Database, TaskScheduleFireRow, TaskScheduleRow
from .platform_tasks import PlatformTaskCreate, PlatformTaskService

MissPolicy = Literal["QUEUE_ONE", "SKIP"]
ScheduleKind = Literal["ONCE", "RECURRING"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TaskScheduleCreate(StrictModel):
    timezone: str = Field(min_length=1, max_length=80)
    kind: ScheduleKind
    once_at: datetime | None = Field(default=None, alias="onceAt")
    rrule: str | None = Field(default=None, max_length=255)
    enabled: bool = True
    miss_policy: MissPolicy = Field(default="QUEUE_ONE", alias="missPolicy")
    start_deadline_minutes: int = Field(default=30, alias="startDeadlineMinutes", ge=1, le=7 * 24 * 60)
    account_id: str = Field(alias="accountId", min_length=1, max_length=36)
    expected_binding_version: int | None = Field(default=None, alias="expectedBindingVersion", ge=1)
    device_ids: list[str] = Field(alias="deviceIds", min_length=1, max_length=100)
    command_type: CommandType = Field(alias="commandType")
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def kind_fields(self) -> TaskScheduleCreate:
        if self.kind == "ONCE" and self.once_at is None:
            raise ValueError("onceAt is required for ONCE schedules")
        if self.kind == "RECURRING" and not self.rrule:
            raise ValueError("rrule is required for RECURRING schedules")
        self.device_ids = list(dict.fromkeys(self.device_ids))
        return self


class ScheduleFireRequest(StrictModel):
    scheduled_for: datetime = Field(alias="scheduledFor")
    device_id: str | None = Field(default=None, alias="deviceId")


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValidationError("timezone is not a valid IANA name") from exc


def next_occurrences(timezone: str, rrule: str, *, after: datetime, count: int = 3) -> list[datetime]:
    zone = _zone(timezone)
    local_after = _aware(after).astimezone(zone)
    # task-schedule/v1 §5 (ruling D3): restricted rrule subset only —
    # FREQ=HOURLY/DAILY/WEEKLY + INTERVAL. RFC5545 is explicitly out of scope.
    rrule_field = {"rrule": "仅支持 FREQ=HOURLY/DAILY/WEEKLY + INTERVAL"}
    if not rrule.startswith("FREQ="):
        raise ValidationError("rrule must start with FREQ=", fields=rrule_field)
    parts = dict(item.split("=", 1) for item in rrule.split(";") if "=" in item)
    freq = parts.get("FREQ")
    try:
        interval = int(parts.get("INTERVAL", "1"))
    except ValueError as exc:
        raise ValidationError("rrule INTERVAL must be an integer", fields=rrule_field) from exc
    if interval < 1:
        raise ValidationError("rrule INTERVAL must be >= 1", fields=rrule_field)
    cursor = local_after.replace(second=0, microsecond=0)
    if freq == "HOURLY":
        step = timedelta(hours=interval)
        cursor = cursor.replace(minute=0) + step
    elif freq == "DAILY":
        step = timedelta(days=interval)
        cursor = (cursor + step).replace(hour=local_after.hour, minute=local_after.minute)
    elif freq == "WEEKLY":
        step = timedelta(days=7 * interval)
        cursor = (cursor + step).replace(hour=local_after.hour, minute=local_after.minute)
    else:
        raise ValidationError(
            "only FREQ=HOURLY,DAILY,WEEKLY are supported", fields=rrule_field
        )
    values: list[datetime] = []
    while len(values) < count:
        values.append(cursor.astimezone(UTC))
        cursor = cursor + step
    return values


def fold_local(timezone: str, value: datetime) -> tuple[datetime, str]:
    zone = _zone(timezone)
    local = _aware(value).astimezone(zone)
    utc = local.replace(tzinfo=None).replace(tzinfo=zone).astimezone(UTC)
    label = local.isoformat()
    if local.fold == 1:
        label += "#fold"
    return utc, label


class TaskScheduleService:
    def __init__(self, database: Database, platform: PlatformTaskService) -> None:
        self.database = database
        self.platform = platform

    async def create(self, actor: Actor, body: TaskScheduleCreate) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.TASK_CREATE)
        _zone(body.timezone)
        if body.kind == "ONCE":
            assert body.once_at is not None
            if _aware(body.once_at) <= _now():
                raise ValidationError("onceAt must be in the future")
        if body.kind == "RECURRING":
            assert body.rrule is not None
            next_occurrences(body.timezone, body.rrule, after=_now(), count=1)
        async with self.database.unit_of_work() as session:
            binding_version = body.expected_binding_version
            for device_id in body.device_ids:
                live = await session.scalar(
                    select(AccountDeviceBindingRow).where(
                        AccountDeviceBindingRow.tenant_id == str(actor.tenant_id),
                        AccountDeviceBindingRow.account_id == body.account_id,
                        AccountDeviceBindingRow.device_id == device_id,
                        AccountDeviceBindingRow.status == "BOUND",
                    )
                )
                if live is None:
                    raise ConflictError("schedule account is not bound to every selected device")
                if body.expected_binding_version is not None and live.binding_version != body.expected_binding_version:
                    raise ConflictError("binding version does not match expectedBindingVersion")
                binding_version = live.binding_version
            row = TaskScheduleRow(
                id=str(uuid.uuid4()),
                tenant_id=str(actor.tenant_id),
                timezone=body.timezone,
                kind=body.kind,
                once_at=_aware(body.once_at) if body.once_at else None,
                rrule=body.rrule,
                enabled=body.enabled,
                template_revision=1,
                miss_policy=body.miss_policy,
                start_deadline_minutes=body.start_deadline_minutes,
                account_id=body.account_id,
                binding_version=binding_version or 1,
                device_ids=body.device_ids,
                command_type=body.command_type,
                parameters=body.parameters,
                created_by=str(actor.user_id),
                paused_reason=None,
                last_error=None,
                created_at=_now(),
            )
            session.add(row)
        return self._view(row)

    async def list_schedules(self, actor: Actor) -> list[dict[str, Any]]:
        require_permissions(actor.roles, Permission.DEVICE_READ)
        async with self.database.unit_of_work() as session:
            rows = list(
                await session.scalars(
                    select(TaskScheduleRow)
                    .where(TaskScheduleRow.tenant_id == str(actor.tenant_id))
                    .order_by(TaskScheduleRow.created_at.desc())
                )
            )
        return [self._view(row) for row in rows]

    async def get(self, actor: Actor, schedule_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_READ)
        async with self.database.unit_of_work() as session:
            row = await self._row(session, actor, schedule_id)
            fires = list(
                await session.scalars(
                    select(TaskScheduleFireRow)
                    .where(TaskScheduleFireRow.schedule_id == row.id)
                    .order_by(TaskScheduleFireRow.scheduled_for.desc())
                )
            )
        view = self._view(row)
        view["fires"] = [self._fire_view(item) for item in fires]
        return view

    async def set_enabled(self, actor: Actor, schedule_id: str, enabled: bool) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.TASK_CREATE)
        async with self.database.unit_of_work() as session:
            row = await self._row(session, actor, schedule_id, for_update=True)
            row.enabled = enabled
            if enabled:
                row.paused_reason = None
            return self._view(row)

    async def fire(
        self, actor: Actor, schedule_id: str, request: ScheduleFireRequest
    ) -> tuple[list[dict[str, Any]], bool]:
        """Fire a schedule occurrence; returns (fire views, created-any flag).

        task-schedule/v1 §5: the fire idempotency key is
        sha256(schedule_id:utc_time:device_id)[:64] and the TaskScheduleFireRow
        Unique(schedule_id, scheduled_for, device_id) is the backstop, so a
        replayed fire returns the existing records without minting new tasks
        (created=False → HTTP 200; first fire → HTTP 201).
        """
        require_permissions(actor.roles, Permission.TASK_CREATE)
        scheduled_for = _aware(request.scheduled_for)
        pending: list[dict[str, Any]] = []
        async with self.database.unit_of_work() as session:
            row = await self._row(session, actor, schedule_id, for_update=True)
            if not row.enabled:
                raise ConflictError("disabled schedules no longer fire")
            snapshot = {
                "id": row.id,
                "kind": row.kind,
                "timezone": row.timezone,
                "rrule": row.rrule,
                "miss_policy": row.miss_policy,
                "start_deadline_minutes": row.start_deadline_minutes,
                "account_id": row.account_id,
                "binding_version": row.binding_version,
                "command_type": row.command_type,
                "parameters": dict(row.parameters or {}),
                "template_revision": row.template_revision,
                "tenant_id": row.tenant_id,
            }
            devices = [request.device_id] if request.device_id else list(row.device_ids)
            now = _now()
            deadline = scheduled_for + timedelta(minutes=row.start_deadline_minutes)
            latest_recurring: datetime | None = None
            if row.kind == "RECURRING" and row.rrule:
                upcoming = next_occurrences(
                    row.timezone, row.rrule, after=scheduled_for - timedelta(seconds=1), count=1
                )
                latest_recurring = upcoming[0] if upcoming else None
            for device_id in devices:
                utc_time, local_label = fold_local(row.timezone, scheduled_for)
                existing = await session.scalar(
                    select(TaskScheduleFireRow).where(
                        TaskScheduleFireRow.schedule_id == row.id,
                        TaskScheduleFireRow.device_id == device_id,
                        TaskScheduleFireRow.scheduled_for == utc_time,
                    )
                )
                if existing is not None:
                    pending.append({"existing": self._fire_view(existing)})
                    continue
                status = "QUEUED"
                detail = None
                if now > deadline and row.kind == "ONCE":
                    status = "EXPIRED"
                    detail = "startDeadline exceeded; one-shot publish is not backfilled"
                elif (
                    row.kind == "RECURRING"
                    and row.miss_policy == "QUEUE_ONE"
                    and latest_recurring is not None
                    and utc_time < latest_recurring
                    and now > utc_time + timedelta(minutes=row.start_deadline_minutes)
                ):
                    status = "SKIPPED"
                    detail = "older period skipped; only the latest period is queued"
                pending.append(
                    {
                        "device_id": device_id,
                        "utc_time": utc_time,
                        "local_label": local_label,
                        "status": status,
                        "detail": detail,
                        "now": now,
                    }
                )
        results: list[dict[str, Any]] = []
        created_any = False
        for item in pending:
            if "existing" in item:
                results.append(item["existing"])
                continue
            task_id = None
            if item["status"] == "QUEUED":
                fire_key = hashlib.sha256(
                    f"{snapshot['id']}:{item['utc_time'].isoformat()}:{item['device_id']}".encode()
                ).hexdigest()[:64]
                created, _ = await self.platform.create(
                    actor,
                    fire_key,
                    PlatformTaskCreate.model_validate(
                        {
                            "deviceId": item["device_id"],
                            "commandType": snapshot["command_type"],
                            "accountId": snapshot["account_id"],
                            "expectedBindingVersion": snapshot["binding_version"],
                            "parameters": snapshot["parameters"],
                            "scheduledFor": item["utc_time"],
                            # §5 parameter freeze: stamp the template revision
                            # this command was minted from.
                            "templateRevision": snapshot["template_revision"],
                        }
                    ),
                )
                task_id = created[0]["taskId"]
            async with self.database.unit_of_work() as session:
                existing = await session.scalar(
                    select(TaskScheduleFireRow).where(
                        TaskScheduleFireRow.schedule_id == snapshot["id"],
                        TaskScheduleFireRow.device_id == item["device_id"],
                        TaskScheduleFireRow.scheduled_for == item["utc_time"],
                    )
                )
                if existing is not None:
                    results.append(self._fire_view(existing))
                    continue
                fire = TaskScheduleFireRow(
                    id=str(uuid.uuid4()),
                    tenant_id=snapshot["tenant_id"],
                    schedule_id=snapshot["id"],
                    device_id=item["device_id"],
                    scheduled_for=item["utc_time"],
                    scheduled_for_local=item["local_label"],
                    status=item["status"],
                    task_id=task_id,
                    detail=item["detail"],
                    created_at=item["now"],
                )
                session.add(fire)
                try:
                    await session.flush()
                except IntegrityError as exc:
                    raise ConflictError("schedule fire already exists") from exc
                created_any = True
                results.append(self._fire_view(fire))
        return results, created_any

    async def pause_account_schedules(self, tenant_id: str, account_id: str, reason: str) -> None:
        async with self.database.unit_of_work() as session:
            rows = list(
                await session.scalars(
                    select(TaskScheduleRow).where(
                        TaskScheduleRow.tenant_id == tenant_id,
                        TaskScheduleRow.account_id == account_id,
                        TaskScheduleRow.enabled.is_(True),
                    )
                )
            )
            for row in rows:
                row.enabled = False
                row.paused_reason = reason

    async def _row(self, session: Any, actor: Actor, schedule_id: str, *, for_update: bool = False) -> TaskScheduleRow:
        statement = select(TaskScheduleRow).where(
            TaskScheduleRow.id == schedule_id,
            TaskScheduleRow.tenant_id == str(actor.tenant_id),
        )
        if for_update:
            statement = statement.with_for_update()
        row = await session.scalar(statement)
        if row is None:
            raise NotFoundError("schedule was not found")
        return row

    def _view(self, row: TaskScheduleRow) -> dict[str, Any]:
        preview: list[str] = []
        if row.kind == "ONCE" and row.once_at is not None:
            preview = [_aware(row.once_at).isoformat()]
        elif row.rrule:
            preview = [item.isoformat() for item in next_occurrences(row.timezone, row.rrule, after=_now(), count=3)]
        return {
            "id": row.id,
            "timezone": row.timezone,
            "kind": row.kind,
            "onceAt": row.once_at,
            "rrule": row.rrule,
            "enabled": row.enabled,
            "templateRevision": row.template_revision,
            "missPolicy": row.miss_policy,
            "startDeadlineMinutes": row.start_deadline_minutes,
            "accountId": row.account_id,
            "bindingVersion": row.binding_version,
            "deviceIds": row.device_ids,
            "commandType": row.command_type,
            "parameters": row.parameters,
            "pausedReason": row.paused_reason,
            "nextOccurrences": preview,
            "createdAt": row.created_at,
        }

    @staticmethod
    def _fire_view(row: TaskScheduleFireRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "scheduleId": row.schedule_id,
            "deviceId": row.device_id,
            "scheduledFor": row.scheduled_for,
            "scheduledForLocal": row.scheduled_for_local,
            "status": row.status,
            "taskId": row.task_id,
            "detail": row.detail,
        }
