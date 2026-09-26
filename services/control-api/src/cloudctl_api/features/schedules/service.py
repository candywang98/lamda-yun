"""F12 fleet schedule service: Temporal-driven due mint + terminal cancel.

Temporal only decides *when* — the worker ticks (poll → deterministic child
workflow per period → mint activity). This service is the single minting
authority: every mint lands on the A04 MobileTask queue through
PlatformTaskService.create with a stable fire key, so a crashed worker, a
replayed activity, or a repeated tick all converge on the same MobileTask
(201 first mint / 200 replay). No second business queue is introduced.

Cancel (F12 §4): cancelling a schedule stops future triggers only. Already
minted tasks keep their device/account — nothing is auto-migrated to another
device or account (a task whose device is offline simply waits on that
device) — and each is cancelled individually via platform-tasks :cancel.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from cloudctl_domain import (
    Actor,
    ConflictError,
    DomainError,
    NotFoundError,
    Permission,
    require_permissions,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import AuditEventRow, Database, TaskScheduleFireRow, TaskScheduleRow
from ...platform_tasks import PlatformTaskCreate, PlatformTaskService
from .fleet_schedule import (
    Occurrence,
    classify_due_occurrences,
    fire_key,
    local_label,
    occurrence_grid,
    period_marker,
    schedule_snapshot,
)
from .models import FleetScheduleControlRow

FIRE_QUEUED = "QUEUED"
FIRE_SKIPPED = "SKIPPED"
FIRE_ERROR = "ERROR"


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class FleetScheduleService:
    def __init__(self, database: Database, platform: PlatformTaskService) -> None:
        self.database = database
        self.platform = platform

    # ------------------------------------------------------------------
    # shared helpers
    # ------------------------------------------------------------------

    async def _schedule_row(
        self, session: AsyncSession, actor: Actor, schedule_id: str, *, for_update: bool = False
    ) -> TaskScheduleRow:
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

    @staticmethod
    async def _control_row(
        session: AsyncSession, schedule_id: str
    ) -> FleetScheduleControlRow | None:
        return cast(
            FleetScheduleControlRow | None,
            await session.scalar(
                select(FleetScheduleControlRow).where(
                    FleetScheduleControlRow.schedule_id == schedule_id
                )
            ),
        )

    @staticmethod
    async def _attempted_markers(
        session: Any, schedule_id: str
    ) -> dict[str, list[TaskScheduleFireRow]]:
        rows = list(
            await session.scalars(
                select(TaskScheduleFireRow).where(TaskScheduleFireRow.schedule_id == schedule_id)
            )
        )
        # A ledger row for any device marks the period as decided (minted,
        # skipped, or errored): decisions are terminal per period.
        attempted: dict[str, list[TaskScheduleFireRow]] = {}
        for row in rows:
            attempted.setdefault(period_marker(_aware(row.scheduled_for)), []).append(row)
        return attempted

    def _due_occurrences(self, snapshot: dict[str, Any], now: datetime) -> list[Occurrence]:
        """Grid points whose scheduled time has arrived, ascending."""
        if snapshot["kind"] == "ONCE":
            once = snapshot["once_at"]
            return (
                [
                    Occurrence(
                        utc=once, local_label=local_label(once, ZoneInfo(snapshot["timezone"]))
                    )
                ]
                if once is not None and once <= now
                else []
            )
        grid = occurrence_grid(
            snapshot["timezone"],
            snapshot["rrule"] or "",
            anchor=snapshot["created_at"],
            through=now,
        )
        return sorted((item for item in grid if item.utc <= now), key=lambda item: item.utc)

    @staticmethod
    def _mint_guard(row: TaskScheduleRow, control: FleetScheduleControlRow | None) -> None:
        if control is not None and control.status == "CANCELLED":
            raise ConflictError(
                "cancelled fleet schedule no longer mints; minted tasks must be "
                "cancelled individually via platform-tasks :cancel"
            )
        if not row.enabled:
            raise ConflictError("disabled schedules no longer mint")

    # ------------------------------------------------------------------
    # mint_due — the Temporal activity target
    # ------------------------------------------------------------------

    async def mint_due(
        self, actor: Actor, schedule_id: str, *, now: datetime | None = None
    ) -> dict[str, Any]:
        """Mint every policy-selected due occurrence of one schedule.

        Idempotent by construction: the fire key is a pure function of
        (schedule_id, occurrence UTC instant, device_id) — A04 create replays
        the same MobileTask on retry, and the ledger's
        Unique(schedule_id, scheduled_for, device_id) backstops partial
        multi-device crashes (devices already minted converge as replays).
        """
        require_permissions(actor.roles, Permission.TASK_CREATE)
        moment = _aware(now) if now else _now()
        async with self.database.unit_of_work() as session:
            row = await self._schedule_row(session, actor, schedule_id, for_update=True)
            control = await self._control_row(session, schedule_id)
            self._mint_guard(row, control)
            snapshot = schedule_snapshot(row)
            attempted = await self._attempted_markers(session, schedule_id)

        due = self._due_occurrences(snapshot, moment)
        unminted = [item for item in due if item.marker not in attempted]
        policy = snapshot["miss_policy"]
        decision = classify_due_occurrences(unminted, policy)

        decisions: list[dict[str, Any]] = []
        task_ids: list[str] = []
        created_any = False

        # Crash recovery / repeated tick: the latest already-attempted due
        # period replays its ledger rows (same tasks, createdAny=False). Only
        # the latest one is echoed so the response stays bounded.
        attempted_due = [item for item in due if item.marker in attempted]
        if attempted_due:
            latest = attempted_due[-1]
            replay_items = [self._fire_view(f, latest) for f in attempted[latest.marker]]
            replay_items.sort(key=lambda item: item["deviceId"])
            task_ids.extend(item["taskId"] for item in replay_items if item.get("taskId"))
            decisions.append(
                {
                    "periodMarker": latest.marker,
                    "scheduledFor": latest.utc,
                    "action": "REPLAY",
                    "detail": "period already decided; idempotent replay of the "
                    "existing fire ledger",
                    "items": replay_items,
                }
            )

        for skip in decision.skipped:
            items = await self._record_skip(snapshot, skip, moment)
            decisions.append(
                {
                    "periodMarker": skip.occurrence.marker,
                    "scheduledFor": skip.occurrence.utc,
                    "action": "SKIP",
                    "detail": skip.detail,
                    "items": items,
                }
            )
        if decision.mint is not None:
            items, minted_ids, minted_any = await self._mint_occurrence(
                actor, snapshot, decision.mint, moment
            )
            task_ids.extend(minted_ids)
            created_any = created_any or minted_any
            decisions.append(
                {
                    "periodMarker": decision.mint.marker,
                    "scheduledFor": decision.mint.utc,
                    "action": "MINT",
                    "detail": None,
                    "items": items,
                }
            )
        decisions.sort(key=lambda item: item["scheduledFor"])
        return {
            "scheduleId": schedule_id,
            "missPolicy": policy,
            "decisions": decisions,
            "taskIds": task_ids,
            "createdAny": created_any,
        }

    async def _mint_occurrence(
        self, actor: Actor, snapshot: dict[str, Any], occurrence: Occurrence, now: datetime
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        """Mint one occurrence on every expanded device; never migrate.

        A device that cannot mint (binding broken, device gone) gets a
        terminal ERROR ledger row on that device — the failure is never
        retried onto a different device or account.
        """
        items: list[dict[str, Any]] = []
        task_ids: list[str] = []
        created_any = False
        for device_id in snapshot["device_ids"]:
            key = fire_key(snapshot["id"], occurrence.utc, device_id)
            task_id: str | None = None
            error_detail: str | None = None
            try:
                views, created = await self.platform.create(
                    actor,
                    key,
                    PlatformTaskCreate.model_validate(
                        {
                            "deviceId": device_id,
                            "commandType": snapshot["command_type"],
                            "accountId": snapshot["account_id"],
                            "expectedBindingVersion": snapshot["binding_version"],
                            "parameters": snapshot["parameters"],
                            "scheduledFor": occurrence.utc,
                            # F12 §2: pin the template revision at mint time —
                            # later template edits never drift a minted task.
                            "templateRevision": snapshot["template_revision"],
                        }
                    ),
                )
                task_id = views[0]["taskId"]
                created_any = created_any or created
            except DomainError as exc:
                error_detail = f"{type(exc).__name__}: {exc.detail}"
            row = await self._upsert_fire_row(
                snapshot,
                device_id,
                occurrence,
                now,
                status=FIRE_ERROR if error_detail else FIRE_QUEUED,
                task_id=task_id,
                detail=error_detail,
            )
            if row.get("taskId"):
                task_ids.append(row["taskId"])
            items.append(row)
        return items, task_ids, created_any

    async def _record_skip(
        self, snapshot: dict[str, Any], skip: Any, now: datetime
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for device_id in snapshot["device_ids"]:
            items.append(
                await self._upsert_fire_row(
                    snapshot,
                    device_id,
                    skip.occurrence,
                    now,
                    status=FIRE_SKIPPED,
                    task_id=None,
                    detail=skip.detail,
                )
            )
        return items

    async def _upsert_fire_row(
        self,
        snapshot: dict[str, Any],
        device_id: str,
        occurrence: Occurrence,
        now: datetime,
        *,
        status: str,
        task_id: str | None,
        detail: str | None,
    ) -> dict[str, Any]:
        fire_id = str(uuid.uuid4())
        try:
            async with self.database.unit_of_work() as session:
                existing = await session.scalar(
                    select(TaskScheduleFireRow).where(
                        TaskScheduleFireRow.schedule_id == snapshot["id"],
                        TaskScheduleFireRow.device_id == device_id,
                        TaskScheduleFireRow.scheduled_for == occurrence.utc,
                    )
                )
                if existing is not None:
                    return self._fire_view(existing, occurrence)
                fire = TaskScheduleFireRow(
                    id=fire_id,
                    tenant_id=snapshot["tenant_id"],
                    schedule_id=snapshot["id"],
                    device_id=device_id,
                    scheduled_for=occurrence.utc,
                    scheduled_for_local=occurrence.local_label or "",
                    status=status,
                    task_id=task_id,
                    detail=detail,
                    created_at=now,
                )
                session.add(fire)
        except IntegrityError:
            # Unique(schedule_id, scheduled_for, device_id) backstop: a
            # concurrent mint of the same period recorded it first — replay.
            async with self.database.unit_of_work() as session:
                existing = await session.scalar(
                    select(TaskScheduleFireRow).where(
                        TaskScheduleFireRow.schedule_id == snapshot["id"],
                        TaskScheduleFireRow.device_id == device_id,
                        TaskScheduleFireRow.scheduled_for == occurrence.utc,
                    )
                )
                if existing is None:
                    raise ConflictError("schedule fire already exists") from None
                return self._fire_view(existing, occurrence)
        view = self._fire_view(fire, occurrence)
        view["status"] = status
        return view

    @staticmethod
    def _fire_view(row: TaskScheduleFireRow, occurrence: Occurrence) -> dict[str, Any]:
        return {
            "scheduleId": row.schedule_id,
            "deviceId": row.device_id,
            "scheduledFor": _aware(row.scheduled_for),
            "scheduledForLocal": row.scheduled_for_local,
            "periodMarker": occurrence.marker,
            "status": row.status,
            "taskId": row.task_id,
            "detail": row.detail,
        }

    # ------------------------------------------------------------------
    # poll_due — the temporal tick index
    # ------------------------------------------------------------------

    async def poll_due(self, actor: Actor, *, now: datetime | None = None) -> dict[str, Any]:
        """List occurrences the worker should mint right now (post-policy).

        Authoritative policy application still happens inside mint_due; this
        is only the tick index so the worker can start one deterministic
        child workflow per period.
        """
        require_permissions(actor.roles, Permission.DEVICE_READ)
        moment = _aware(now) if now else _now()
        items: list[dict[str, Any]] = []
        async with self.database.unit_of_work() as session:
            rows = list(
                await session.scalars(
                    select(TaskScheduleRow).where(
                        TaskScheduleRow.tenant_id == str(actor.tenant_id),
                        TaskScheduleRow.enabled.is_(True),
                    )
                )
            )
            cancelled_ids = {
                control.schedule_id
                for control in await session.scalars(
                    select(FleetScheduleControlRow).where(
                        FleetScheduleControlRow.tenant_id == str(actor.tenant_id),
                        FleetScheduleControlRow.status == "CANCELLED",
                    )
                )
            }
            for row in rows:
                if row.id in cancelled_ids:
                    continue
                snapshot = schedule_snapshot(row)
                attempted = await self._attempted_markers(session, row.id)
                due = self._due_occurrences(snapshot, moment)
                unminted = [item for item in due if item.marker not in attempted]
                decision = classify_due_occurrences(unminted, snapshot["miss_policy"])
                if decision.mint is None:
                    continue
                items.append(
                    {
                        "scheduleId": row.id,
                        "periodMarker": decision.mint.marker,
                        "scheduledFor": decision.mint.utc,
                        "timezone": snapshot["timezone"],
                    }
                )
        return {"items": items, "count": len(items)}

    # ------------------------------------------------------------------
    # cancel — terminal, future-only, per-task downstream
    # ------------------------------------------------------------------

    async def cancel(self, actor: Actor, schedule_id: str, reason: str) -> dict[str, Any]:
        """Cancel a schedule: future triggers stop, minted tasks stay.

        Idempotent: cancelling an already-cancelled schedule replays the view.
        The legacy row is also disabled so the frozen manual :fire route stops
        firing too; the control row keeps the terminal state that :enable
        cannot clear (documented seam: a legacy re-enable would still allow
        manual fires, but never fleet mints).
        """
        require_permissions(actor.roles, Permission.TASK_CREATE)
        now = _now()
        async with self.database.unit_of_work() as session:
            row = await self._schedule_row(session, actor, schedule_id, for_update=True)
            control = await self._control_row(session, schedule_id)
            replay = control is not None and control.status == "CANCELLED"
            if control is None:
                control = FleetScheduleControlRow(
                    id=str(uuid.uuid4()),
                    tenant_id=str(actor.tenant_id),
                    schedule_id=schedule_id,
                    status="ACTIVE",
                    created_at=now,
                )
                session.add(control)
            fires = list(
                await session.scalars(
                    select(TaskScheduleFireRow).where(
                        TaskScheduleFireRow.schedule_id == schedule_id,
                        TaskScheduleFireRow.task_id.is_not(None),
                    )
                )
            )
            minted_task_ids = sorted({fire.task_id for fire in fires if fire.task_id})
            if not replay:
                control.status = "CANCELLED"
                control.cancelled_at = now
                control.cancelled_by = f"operator:{actor.user_id}"[:64]
                control.cancel_reason = reason[:500]
                row.enabled = False
                row.paused_reason = f"CANCELLED: {reason}"[:160]
                session.add(
                    AuditEventRow(
                        id=str(uuid.uuid4()),
                        tenant_id=str(actor.tenant_id),
                        actor_type="operator",
                        actor_id=str(actor.user_id)[:255],
                        action="fleet.schedule.cancelled",
                        resource_type="task_schedule",
                        resource_id=schedule_id,
                        request_id=str(uuid.uuid4()),
                        device_id=None,
                        result="SUCCEEDED",
                        metadata_json={
                            "scheduleId": schedule_id,
                            "reason": reason[:160],
                            "mintedTaskIds": minted_task_ids,
                            "autoCancelledTasks": False,
                        },
                        occurred_at=now,
                    )
                )
        return {
            "scheduleId": schedule_id,
            "status": "CANCELLED",
            "cancelledAt": control.cancelled_at,
            "cancelledBy": control.cancelled_by,
            "cancelReason": control.cancel_reason,
            "mintedTaskIds": minted_task_ids,
        }
