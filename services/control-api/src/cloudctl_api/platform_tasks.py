"""Business PlatformTask facade over MobileTask. Does not create a second queue."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from cloudctl_domain import (
    Actor,
    ConflictError,
    NotFoundError,
    Permission,
    ValidationError,
    require_permissions,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from .builtin_recipes import builtin_recipe_ref
from .command_factory import mint_operation_command
from .command_v1 import COMMAND_PACKAGES, CommandType
from .db import (
    AccountDeviceBindingRow,
    AuditEventRow,
    Database,
    DeviceLeaseRow,
    DeviceRow,
    MobileActionCommitRow,
    MobileTaskEventRow,
    MobileTaskRow,
    ProductMediaRow,
    ProductRow,
)
from .mobile_actions import audit_action
from .mobile_schemas import MobileTaskCreate
from .mobile_service import COMPANION_PACKAGE, XIANYU_PACKAGE, MobileTaskService, _aware
from .xianyu_publish import build_text_publish_task, listing_copy_from_parameters

XHS_PACKAGE = "com.xingin.xhs"
BUSINESS_STATES = (
    "QUEUED",
    "WAITING_MATERIALS",
    "PREFLIGHT",
    "RUNNING",
    "PAUSE_REQUESTED",
    "PAUSED_WAITING_USER",
    "RESUME_CHECK",
    "RECONCILING",
    "CANCEL_REQUESTED",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
    "EXPIRED",
)
TERMINAL_BUSINESS = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"})
SAFE_RETRY_CODES = frozenset(
    {
        "LOCATOR_NOT_FOUND",
        "STEP_TIMEOUT",
        "APP_NOT_FOREGROUND",
        "NETWORK_UNAVAILABLE",
        "PREFLIGHT_FAILED",
    }
)
UNSAFE_RETRY_CODES = frozenset(
    {"ACCOUNT_CHANGED", "COMMIT_UNKNOWN", "XIANYU_PUBLISH_SUCCESS", "RECONCILING"}
)
RECONCILE_DECISIONS = {"CONFIRMED_APPLIED", "CONFIRMED_NOT_SUBMITTED", "KEEP_WAITING"}
RUNNER_TO_BUSINESS = {
    "QUEUED": "QUEUED",
    "CLAIMED": "PREFLIGHT",
    "RUNNING": "RUNNING",
    "SUCCEEDED": "SUCCEEDED",
    "FAILED": "FAILED",
}


# ---------------------------------------------------------------------------
# A12 control-transition matrix (fleet-identity/v1 §5/§8, task-schedule/v1 §4)
# ---------------------------------------------------------------------------
# The legal ordering of cancel / pause / ack-paused / resume against every
# business state is pinned here as one explicit table per action. Each table is
# total over BUSINESS_STATES and its values come from a closed outcome set —
# both properties are asserted at import time and mirrored by
# tests/integration/test_fleet_cancel_reconcile.py, so a control decision can
# never fall through a scattered if-chain: it is read from the matrix.
#
# commit-intent modifier (task-schedule/v1 §4): a task whose command payload
# carries a written commitIntent is inside the post-commit window regardless of
# its current state — cancel is refused (409, converge via :reconcile) and an
# ack-paused redirects to RECONCILING. The matrix stays state-pure; the
# modifier is applied at the single decision point via _has_commit_intent.

CANCEL_OUTCOMES = frozenset(
    {
        "CANCELLED_NOW",  # not started / executor parked: settle CANCELLED now
        "CANCEL_REQUESTED",  # live executor: deferred to the next safe point
        "IDEMPOTENT_RETURN",  # duplicate control event: replay the current view
        "REJECTED_RECONCILE_FIRST",  # uncertain result must converge first (409)
        "REJECTED_TERMINAL",  # already settled with a different outcome (409)
    }
)
CANCEL_TRANSITIONS: dict[str, str] = {
    "QUEUED": "CANCELLED_NOW",
    "WAITING_MATERIALS": "CANCELLED_NOW",
    "PREFLIGHT": "CANCELLED_NOW",
    "PAUSE_REQUESTED": "CANCELLED_NOW",
    "PAUSED_WAITING_USER": "CANCELLED_NOW",
    "RUNNING": "CANCEL_REQUESTED",
    "RESUME_CHECK": "CANCEL_REQUESTED",
    "CANCEL_REQUESTED": "IDEMPOTENT_RETURN",
    "RECONCILING": "REJECTED_RECONCILE_FIRST",
    "SUCCEEDED": "REJECTED_TERMINAL",
    "FAILED": "REJECTED_TERMINAL",
    "CANCELLED": "IDEMPOTENT_RETURN",
    "EXPIRED": "REJECTED_TERMINAL",
}

PAUSE_OUTCOMES = frozenset(
    {
        "PAUSE_REQUESTED",
        "IDEMPOTENT_RETURN",
        "REJECTED_CANCEL_WINS",
        "REJECTED_RECONCILE_FIRST",
        "REJECTED_TERMINAL",
    }
)
PAUSE_TRANSITIONS: dict[str, str] = {
    "QUEUED": "PAUSE_REQUESTED",
    "WAITING_MATERIALS": "PAUSE_REQUESTED",
    "PREFLIGHT": "PAUSE_REQUESTED",
    "RUNNING": "PAUSE_REQUESTED",
    "RESUME_CHECK": "PAUSE_REQUESTED",
    "PAUSE_REQUESTED": "IDEMPOTENT_RETURN",
    "PAUSED_WAITING_USER": "IDEMPOTENT_RETURN",
    "CANCEL_REQUESTED": "REJECTED_CANCEL_WINS",
    "RECONCILING": "REJECTED_RECONCILE_FIRST",
    "SUCCEEDED": "REJECTED_TERMINAL",
    "FAILED": "REJECTED_TERMINAL",
    "CANCELLED": "REJECTED_TERMINAL",
    "EXPIRED": "REJECTED_TERMINAL",
}

ACK_PAUSED_OUTCOMES = frozenset(
    {
        "PAUSED_WAITING_USER",
        "IDEMPOTENT_RETURN",
        "REJECTED_CANCEL_WINS",
        "REJECTED_SUPERSEDED",
        "REJECTED_RECONCILE_FIRST",
        "REJECTED_TERMINAL",
    }
)
ACK_PAUSED_TRANSITIONS: dict[str, str] = {
    "QUEUED": "PAUSED_WAITING_USER",
    "WAITING_MATERIALS": "PAUSED_WAITING_USER",
    "PREFLIGHT": "PAUSED_WAITING_USER",
    "RUNNING": "PAUSED_WAITING_USER",
    "PAUSE_REQUESTED": "PAUSED_WAITING_USER",
    "PAUSED_WAITING_USER": "IDEMPOTENT_RETURN",
    # A12 out-of-order: resume already superseded the pause request; a late ack
    # must not drag the task back into a manual-wait state.
    "RESUME_CHECK": "REJECTED_SUPERSEDED",
    "CANCEL_REQUESTED": "REJECTED_CANCEL_WINS",
    "RECONCILING": "REJECTED_RECONCILE_FIRST",
    "SUCCEEDED": "REJECTED_TERMINAL",
    "FAILED": "REJECTED_TERMINAL",
    "CANCELLED": "REJECTED_TERMINAL",
    "EXPIRED": "REJECTED_TERMINAL",
}

RESUME_OUTCOMES = frozenset(
    {
        "RESUME_CHECK",
        "REJECTED_CANCEL_WINS",
        "REJECTED_RECONCILE_FIRST",
        "REJECTED_REQUIRES_PAUSE_ACK",
    }
)
RESUME_TRANSITIONS: dict[str, str] = {
    "PAUSED_WAITING_USER": "RESUME_CHECK",
    "QUEUED": "REJECTED_REQUIRES_PAUSE_ACK",
    "WAITING_MATERIALS": "REJECTED_REQUIRES_PAUSE_ACK",
    "PREFLIGHT": "REJECTED_REQUIRES_PAUSE_ACK",
    "RUNNING": "REJECTED_REQUIRES_PAUSE_ACK",
    "PAUSE_REQUESTED": "REJECTED_REQUIRES_PAUSE_ACK",
    "RESUME_CHECK": "REJECTED_REQUIRES_PAUSE_ACK",
    "CANCEL_REQUESTED": "REJECTED_CANCEL_WINS",
    "RECONCILING": "REJECTED_RECONCILE_FIRST",
    "SUCCEEDED": "REJECTED_REQUIRES_PAUSE_ACK",
    "FAILED": "REJECTED_REQUIRES_PAUSE_ACK",
    "CANCELLED": "REJECTED_CANCEL_WINS",
    "EXPIRED": "REJECTED_REQUIRES_PAUSE_ACK",
}

# The tables are total and closed — assert it in code, not only in tests.
assert frozenset(CANCEL_TRANSITIONS) == frozenset(BUSINESS_STATES)
assert frozenset(PAUSE_TRANSITIONS) == frozenset(BUSINESS_STATES)
assert frozenset(ACK_PAUSED_TRANSITIONS) == frozenset(BUSINESS_STATES)
assert frozenset(RESUME_TRANSITIONS) == frozenset(BUSINESS_STATES)
assert set(CANCEL_TRANSITIONS.values()) <= CANCEL_OUTCOMES
assert set(PAUSE_TRANSITIONS.values()) <= PAUSE_OUTCOMES
assert set(ACK_PAUSED_TRANSITIONS.values()) <= ACK_PAUSED_OUTCOMES
assert set(RESUME_TRANSITIONS.values()) <= RESUME_OUTCOMES


def _business_state_of(row: MobileTaskRow) -> str:
    state = row.business_state or RUNNER_TO_BUSINESS.get(row.status, row.status)
    # task-schedule/v1 D4: legacy single-L rows stay readable for decisions;
    # new writes are double-L CANCELLED only.
    return "CANCELLED" if state == "CANCELED" else state


def _has_commit_intent(row: MobileTaskRow) -> bool:
    return "commitIntent" in (row.command_payload or {})


# ---------------------------------------------------------------------------
# A12 persisted control events with a per-task monotonic revision
# ---------------------------------------------------------------------------
# Cloud-issued control decisions (cancel/pause/resume/mark-unknown/reconcile
# verdicts) and the device's pause acknowledgement are persisted on the task
# row's dynamic steps header (the same header that carries controlEpoch /
# fleetSessionId — never part of payloadIdentity, whose formula only covers
# entries with an "action" key). Revisions increase monotonically per task;
# duplicate control events replay idempotently without minting a revision.

CONTROL_EVENTS_HEADER_KEY = "controlEvents"
CONTROL_REVISION_HEADER_KEY = "controlRevision"
MAX_CONTROL_EVENTS = 50
CONTROL_EVENT_KINDS = frozenset(
    {
        "CANCEL_REQUESTED",
        "CANCELLED",
        "PAUSE_REQUESTED",
        "PAUSE_ACKED",
        "PAUSE_ACKED_RECONCILING",
        "RESUMED",
        "MARKED_UNKNOWN",
        "RECONCILED_APPLIED",
        "RECONCILED_NOT_SUBMITTED",
        "RECONCILED_KEEP_WAITING",
    }
)

# D11：UNKNOWN 证据不随一般 retention 过期——对账标记与其三种裁决是
# 不确定结果唯一的持久证据，压缩时永不丢弃。
PROTECTED_CONTROL_EVENT_KINDS = frozenset(
    {
        "MARKED_UNKNOWN",
        "RECONCILED_APPLIED",
        "RECONCILED_NOT_SUBMITTED",
        "RECONCILED_KEEP_WAITING",
    }
)


def _retain_control_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the newest MAX_CONTROL_EVENTS entries plus every protected event."""
    retained = events[-MAX_CONTROL_EVENTS:]
    protected = [
        event
        for event in events[:-MAX_CONTROL_EVENTS]
        if event.get("event") in PROTECTED_CONTROL_EVENT_KINDS
    ]
    return protected + retained if protected else retained



def _record_control_event(
    row: MobileTaskRow, kind: str, reason: str, actor: str, now: datetime
) -> int:
    """Append one persistent control event and return its revision."""
    assert kind in CONTROL_EVENT_KINDS  # closed event vocabulary
    header = dict(row.steps[0]) if row.steps else {}
    events = list(header.get(CONTROL_EVENTS_HEADER_KEY) or [])
    revision = int(header.get(CONTROL_REVISION_HEADER_KEY) or 0) + 1
    events.append(
        {
            "revision": revision,
            "event": kind,
            "reason": (reason or "")[:160],
            "actor": (actor or "")[:128],
            "issuedAt": now.isoformat(),
        }
    )
    header[CONTROL_REVISION_HEADER_KEY] = revision
    header[CONTROL_EVENTS_HEADER_KEY] = _retain_control_events(events)
    row.steps = [header, *(row.steps[1:] if row.steps else [])]
    return revision


def _control_view(row: MobileTaskRow) -> tuple[int | None, list[dict[str, Any]]]:
    header = (row.steps or [{}])[0] or {}
    return header.get(CONTROL_REVISION_HEADER_KEY), list(
        header.get(CONTROL_EVENTS_HEADER_KEY) or []
    )


def _audit_control_event(
    session: Any,
    row: MobileTaskRow,
    *,
    action: str,
    revision: int,
    actor_id: str,
    actor_type: str = "operator",
    extra: dict[str, Any] | None = None,
) -> None:
    """A12 任务卡 #3: 结案/控制决策必须带审计——每次决策落一条 audit 行。"""
    session.add(
        AuditEventRow(
            id=str(uuid.uuid4()),
            tenant_id=row.tenant_id,
            actor_type=actor_type,
            actor_id=actor_id[:255],
            action=f"platform.task.{action}",
            resource_type="mobile_task",
            resource_id=row.id,
            request_id=str(uuid.uuid4()),
            device_id=row.device_id,
            result="SUCCEEDED",
            metadata_json={
                "taskId": row.id,
                "controlRevision": revision,
                "businessState": row.business_state,
                **(extra or {}),
            },
            occurred_at=_now(),
        )
    )


async def _release_occupation(session: Any, row: MobileTaskRow, now: datetime) -> bool:
    """A12: settling a task by cancel must release the device lease occupation.

    Only the lease owned by this task's AUTO workflow is touched — a REMOTE or
    foreign workflow lease is never force-released here.
    """
    lease = await session.get(DeviceLeaseRow, row.device_id, with_for_update=True)
    if (
        lease is None
        or lease.canceled_at is not None
        or lease.tenant_id != row.tenant_id
        or lease.owner_type != "AUTO"
        or lease.owner_workflow_id != f"auto/{row.id}"
    ):
        return False
    lease.canceled_at = now
    return True


# ---------------------------------------------------------------------------
# A12 read-only window proof (fleet-identity/v1 §8, task card #4)
# ---------------------------------------------------------------------------

READONLY_WINDOW_VERDICTS = frozenset(
    {"ALLOWED", "BLOCKED_EXECUTOR_LIVE", "BLOCKED_OCCUPANCY_LIVE"}
)


async def evaluate_readonly_window(
    session: Any, tenant_id: str, device_id: str, *, now: datetime | None = None
) -> dict[str, Any]:
    """Decide whether a device still carrying pending/uncertain work may take
    an unrelated READ-ONLY task. ``ALLOWED`` requires both proofs:

    * old executor stopped — no CLAIMED task and no RUNNING task holding an
      unexpired lease (lease expiry is the system-wide fencing proof: every
      write path validates the lease, exactly like claim does);
    * window safe — no live device lease of any owner type remains (AUTO or
      REMOTE occupancy keeps the window closed).

    The verdict is pure: it never resolves or clears UNKNOWN ledger rows and
    never unlocks the device — claim keeps answering 409 RECONCILE_REQUIRED
    until an explicit reconciliation converges them (KEEP_WAITING semantics).
    """
    from .fleet_identity import open_unknown_actions

    moment = now or _now()
    tasks = list(
        await session.scalars(
            select(MobileTaskRow).where(
                MobileTaskRow.tenant_id == tenant_id,
                MobileTaskRow.device_id == device_id,
            )
        )
    )

    def lease_live(task: MobileTaskRow) -> bool:
        return task.lease_expires_at is not None and _aware(task.lease_expires_at) > moment

    executor_live = [
        task
        for task in tasks
        if task.status == "CLAIMED" or (task.status == "RUNNING" and lease_live(task))
    ]
    leases = list(
        await session.scalars(
            select(DeviceLeaseRow).where(
                DeviceLeaseRow.tenant_id == tenant_id,
                DeviceLeaseRow.device_id == device_id,
                DeviceLeaseRow.canceled_at.is_(None),
            )
        )
    )
    live_leases = [lease for lease in leases if _aware(lease.expires_at) > moment]
    if executor_live:
        verdict = "BLOCKED_EXECUTOR_LIVE"
    elif live_leases:
        verdict = "BLOCKED_OCCUPANCY_LIVE"
    else:
        verdict = "ALLOWED"
    open_unknown = await open_unknown_actions(session, tenant_id, device_id)
    return {
        "verdict": verdict,
        "proof": {
            "executorLiveTasks": [
                {
                    "taskId": task.id,
                    "status": task.status,
                    "businessState": task.business_state,
                }
                for task in executor_live
            ],
            "liveLeases": [
                {
                    "leaseId": lease.lease_id,
                    "ownerType": lease.owner_type,
                    "ownerWorkflowId": lease.owner_workflow_id,
                    "expiresAt": lease.expires_at,
                }
                for lease in live_leases
            ],
            "openUnknownActions": len(open_unknown),
            "reconcilingTasks": sorted(
                task.id for task in tasks if _business_state_of(task) == "RECONCILING"
            ),
        },
    }


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PlatformTaskRetry(StrictModel):
    reason: str = Field(min_length=3, max_length=500)


class PlatformTaskPause(StrictModel):
    reason: str = Field(min_length=3, max_length=500)


class PlatformTaskReconcile(StrictModel):
    decision: str
    evidence: str = Field(min_length=3, max_length=2000)
    platform_item_id: str | None = Field(default=None, alias="platformItemId")

    @model_validator(mode="after")
    def known_decision(self) -> PlatformTaskReconcile:
        if self.decision not in RECONCILE_DECISIONS:
            raise ValueError(
                "decision must be CONFIRMED_APPLIED, CONFIRMED_NOT_SUBMITTED, or KEEP_WAITING"
            )
        return self


class PlatformTaskResume(StrictModel):
    reason: str = Field(min_length=3, max_length=500)
    page_verified: bool = Field(default=False, alias="pageVerified")


class CompanionControlAck(StrictModel):
    lease_id: str | None = Field(default=None, alias="leaseId")


class PlatformTaskCreate(StrictModel):
    device_id: str | None = Field(default=None, alias="deviceId", min_length=1, max_length=36)
    device_ids: list[str] = Field(default_factory=list, alias="deviceIds", max_length=100)
    command_type: CommandType | None = Field(default=None, alias="commandType")
    account_id: str = Field(alias="accountId", min_length=1, max_length=36)
    expected_binding_version: int | None = Field(default=None, alias="expectedBindingVersion", ge=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    media_delivery_id: str | None = Field(default=None, alias="mediaDeliveryId")
    product_id: str | None = Field(default=None, alias="productId", min_length=1, max_length=36)
    batch_id: str | None = Field(default=None, alias="batchId", min_length=1, max_length=36)
    scheduled_for: datetime | None = Field(default=None, alias="scheduledFor")
    publish_target_id: str | None = Field(default=None, alias="publishTargetId")
    operation_id: str | None = Field(default=None, alias="operationId", min_length=1, max_length=64)
    # task-schedule/v1 §5 parameter freeze: schedule fire stamps the template
    # revision it minted from so later template edits cannot drift a fired task.
    template_revision: int | None = Field(default=None, alias="templateRevision", ge=1, le=10000)

    @model_validator(mode="after")
    def require_devices_and_command(self) -> PlatformTaskCreate:
        ids = list(self.device_ids)
        if self.device_id:
            ids = [self.device_id, *ids]
        unique = list(dict.fromkeys(ids))
        if not unique:
            raise ValueError("deviceId or deviceIds is required")
        object.__setattr__(self, "device_ids", unique)
        if self.operation_id:
            minted = mint_operation_command(self.operation_id, self.parameters)
            if self.command_type and self.command_type != minted["commandType"]:
                raise ValueError("operationId does not match commandType")
            object.__setattr__(self, "command_type", minted["commandType"])
            object.__setattr__(self, "parameters", minted["parameters"])
        if not self.command_type:
            raise ValueError("commandType or operationId is required")
        return self


def _now() -> datetime:
    return datetime.now(UTC)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


async def _settle_reply_delivery(session: Any, task_id: str, business_state: str) -> None:
    """Forward terminal task state to the bound IM reply OUT message."""
    from .im_service import settle_reply_delivery

    await settle_reply_delivery(session, task_id, business_state)


def _probe_steps() -> list[dict[str, Any]]:
    return [
        {
            "stepId": "probe-capabilities",
            "action": "run.log",
            "level": "INFO",
            "messageCode": "DEVICE_PROBE_CAPABILITIES",
            "timeoutMs": 1_000,
        }
    ]


def _xhs_note_steps() -> list[dict[str, Any]]:
    return [
        {
            "stepId": "mark-note-frozen",
            "action": "run.log",
            "level": "INFO",
            "messageCode": "XHS_NOTE_SNAPSHOT_FROZEN",
            "timeoutMs": 1_000,
        }
    ]


class PlatformTaskService:
    def __init__(self, database: Database, mobile: MobileTaskService) -> None:
        self.database = database
        self.mobile = mobile

    async def create(
        self, actor: Actor, key: str, body: PlatformTaskCreate
    ) -> tuple[list[dict[str, Any]], bool]:
        require_permissions(actor.roles, Permission.TASK_CREATE)
        if not key or len(key) > 100:
            raise ValidationError("Idempotency-Key is required and must be at most 100 characters")
        body = await self._freeze_publish_listing(actor, body)
        batch_id = body.batch_id or str(uuid.uuid4())
        created_any = False
        views: list[dict[str, Any]] = []
        for device_id in body.device_ids:
            mobile_body = self._mobile_body(device_id, body)
            per_key = f"{key}:{device_id}" if len(body.device_ids) > 1 else key
            view, created = await self.mobile._insert_task(
                tenant_id=str(actor.tenant_id),
                requested_by=str(actor.user_id),
                key=per_key,
                body=mobile_body,
            )
            created_any = created_any or created
            command_payload = {
                "commandType": body.command_type,
                "parameters": body.parameters,
                "accountId": body.account_id,
                "expectedBindingVersion": body.expected_binding_version,
                "publishTargetId": body.publish_target_id,
                "productId": body.product_id or body.parameters.get("productId"),
                "mediaDeliveryId": body.media_delivery_id,
                "snapshotId": f"snap-{view['taskId']}",
                "recipe": builtin_recipe_ref(body.command_type),
            }
            # task-schedule/v1 §2/D1: freeze the minting operationId into the
            # snapshot; §5: freeze the template revision the command was minted from.
            if body.operation_id:
                command_payload["operationId"] = body.operation_id
            if body.template_revision is not None:
                command_payload["templateRevision"] = body.template_revision
            command_payload["snapshotSha256"] = hashlib.sha256(
                _canonical(command_payload).encode()
            ).hexdigest()
            await self._stamp_business_fields(
                task_id=view["taskId"],
                command_type=body.command_type,
                command_payload=command_payload,
                batch_id=batch_id,
                scheduled_for=body.scheduled_for,
                operation_id=body.operation_id,
            )
            views.append(await self.get(actor, view["taskId"]))
        return views, created_any

    async def list_tasks(
        self,
        actor: Actor,
        *,
        after: str | None,
        limit: int,
        device_id: str | None,
        batch_id: str | None,
        state: str | None,
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_READ)
        if limit < 1 or limit > 100:
            raise ValidationError("limit must be between 1 and 100")
        tenant_id = str(actor.tenant_id)
        async with self.database.unit_of_work() as session:
            statement = select(MobileTaskRow).where(MobileTaskRow.tenant_id == tenant_id)
            if device_id:
                statement = statement.where(MobileTaskRow.device_id == device_id)
            if batch_id:
                statement = statement.where(MobileTaskRow.batch_id == batch_id)
            if state:
                statement = statement.where(MobileTaskRow.business_state == state)
            if after:
                cursor = await session.get(MobileTaskRow, after)
                if cursor is None or cursor.tenant_id != tenant_id:
                    raise NotFoundError("cursor task was not found")
                statement = statement.where(
                    (MobileTaskRow.created_at < cursor.created_at)
                    | (
                        (MobileTaskRow.created_at == cursor.created_at)
                        & (MobileTaskRow.id < cursor.id)
                    )
                )
            rows = list(
                await session.scalars(
                    statement.order_by(
                        MobileTaskRow.created_at.desc(), MobileTaskRow.id.desc()
                    ).limit(limit + 1)
                )
            )
        page = rows[:limit]
        next_cursor = page[-1].id if len(rows) > limit else None
        return {
            "items": [self._business_view(row) for row in page],
            "nextCursor": next_cursor,
            "limit": limit,
        }

    async def get(self, actor: Actor, task_id: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_READ)
        async with self.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id)
            if row is None or row.tenant_id != str(actor.tenant_id):
                raise NotFoundError("platform task was not found")
            events = list(
                await session.scalars(
                    select(MobileTaskEventRow)
                    .where(MobileTaskEventRow.task_id == task_id)
                    .order_by(MobileTaskEventRow.sequence)
                )
            )
        view = self._business_view(row)
        view["events"] = [self._event_view(event) for event in events]
        return view

    async def cancel(self, actor: Actor, task_id: str, reason: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.TASK_CREATE)
        now = _now()
        async with self.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id, with_for_update=True)
            if row is None or row.tenant_id != str(actor.tenant_id):
                raise NotFoundError("platform task was not found")
            # A12: the decision is read from the explicit transition matrix.
            outcome = CANCEL_TRANSITIONS[_business_state_of(row)]
            if outcome == "IDEMPOTENT_RETURN":
                # Duplicate cancel event: replay idempotently, no new revision.
                return self._business_view(row)
            if outcome == "REJECTED_TERMINAL":
                raise ConflictError("terminal platform task cannot be canceled")
            if outcome == "REJECTED_RECONCILE_FIRST":
                raise ConflictError("uncertain result must be reconciled before cancellation")
            if _has_commit_intent(row):
                # Post-commit window (legacy marker): cancellation must not erase
                # the uncertain outcome — converge through :reconcile instead.
                raise ConflictError("uncertain result must be reconciled before cancellation")
            if outcome == "CANCEL_REQUESTED":
                revision = _record_control_event(
                    row, "CANCEL_REQUESTED", reason, f"operator:{actor.user_id}", now
                )
                row.business_state = "CANCEL_REQUESTED"
                row.stall_reason = reason[:160]
                _audit_control_event(
                    session,
                    row,
                    action="cancel_requested",
                    revision=revision,
                    actor_id=str(actor.user_id),
                    extra={"reason": reason[:160]},
                )
                return self._business_view(row)
            row.status = "FAILED"
            row.business_state = "CANCELLED"
            row.error_code = "CANCELLED"
            row.detail = reason
            row.completed_at = now
            row.lease_id = None
            row.lease_expires_at = None
            # A12: the local occupation (device lease) is released with the
            # cancel so the same device can immediately claim new work.
            occupation_released = await _release_occupation(session, row, now)
            revision = _record_control_event(
                row, "CANCELLED", reason, f"operator:{actor.user_id}", now
            )
            _audit_control_event(
                session,
                row,
                action="cancelled",
                revision=revision,
                actor_id=str(actor.user_id),
                extra={"occupationReleased": occupation_released},
            )
            await _settle_reply_delivery(session, row.id, "CANCELLED")
            return self._business_view(row)

    async def retry(self, actor: Actor, task_id: str, request: PlatformTaskRetry) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.TASK_CREATE)
        async with self.database.unit_of_work() as session:
            source = await session.get(MobileTaskRow, task_id, with_for_update=True)
            if source is None or source.tenant_id != str(actor.tenant_id):
                raise NotFoundError("platform task was not found")
            if source.business_state == "RECONCILING":
                raise ConflictError("uncertain result must be reconciled before retry")
            if source.business_state != "FAILED" and source.status != "FAILED":
                raise ConflictError("only a failed task can be retried")
            if source.error_code in UNSAFE_RETRY_CODES:
                raise ConflictError(
                    "uncertain or binding-changed failures must be reconciled first"
                )
            if source.error_code and source.error_code not in SAFE_RETRY_CODES:
                raise ConflictError("this failure is not classified as safely retryable")
            payload = dict(source.command_payload or {})
            retry_body = {
                "deviceId": source.device_id,
                "commandType": source.command_type
                or payload.get("commandType")
                or "device.probe_capabilities.v1",
                "accountId": source.account_id or payload.get("accountId"),
                "expectedBindingVersion": source.binding_version,
                "parameters": payload.get("parameters") or {},
                "publishTargetId": payload.get("publishTargetId"),
                "productId": payload.get("productId"),
                "mediaDeliveryId": payload.get("mediaDeliveryId"),
                # task-schedule/v1 §2: retries keep the original catalog identity
                # and frozen template revision instead of re-deriving them.
                "operationId": source.operation_id or payload.get("operationId"),
                "templateRevision": payload.get("templateRevision"),
            }
            retry_key = f"retry:{source.id}:{source.attempt + 1}:{request.reason[:24]}"
        body = PlatformTaskCreate.model_validate(retry_body)
        views, _ = await self.create(actor, retry_key, body)
        return views[0]

    async def mark_unknown(self, actor: Actor, task_id: str, reason: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.TASK_CREATE)
        now = _now()
        async with self.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id, with_for_update=True)
            if row is None or row.tenant_id != str(actor.tenant_id):
                raise NotFoundError("platform task was not found")
            current = _business_state_of(row)
            if current in TERMINAL_BUSINESS or row.status == "SUCCEEDED":
                raise ConflictError("terminal tasks cannot enter reconciliation")
            row.business_state = "RECONCILING"
            row.stall_reason = reason[:160]
            row.reconciliation = {
                **dict(row.reconciliation or {}),
                "status": "UNKNOWN",
                "reason": reason,
                "history": list((row.reconciliation or {}).get("history") or []),
            }
            revision = _record_control_event(
                row, "MARKED_UNKNOWN", reason, f"operator:{actor.user_id}", now
            )
            _audit_control_event(
                session,
                row,
                action="marked_unknown",
                revision=revision,
                actor_id=str(actor.user_id),
            )
            return self._business_view(row)

    async def reconcile(
        self, actor: Actor, task_id: str, request: PlatformTaskReconcile
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.TASK_CREATE)
        now = _now()
        async with self.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id, with_for_update=True)
            if row is None or row.tenant_id != str(actor.tenant_id):
                raise NotFoundError("platform task was not found")
            if row.business_state in TERMINAL_BUSINESS:
                raise ConflictError("terminal tasks cannot be reconciled again")
            if row.business_state != "RECONCILING" and row.error_code not in {
                "COMMIT_UNKNOWN",
                "RECONCILING",
            }:
                raise ConflictError("only RECONCILING tasks can be reconciled")
            actions = list(await session.scalars(
                select(MobileActionCommitRow)
                .where(MobileActionCommitRow.task_id == row.id)
                .with_for_update()
            ))
            if request.decision == "CONFIRMED_NOT_SUBMITTED" and any(
                action.status == "APPLIED" for action in actions
            ):
                raise ConflictError("reported APPLIED evidence contradicts NOT_SUBMITTED")
            if request.decision != "KEEP_WAITING":
                for action in actions:
                    action.status = (
                        "APPLIED" if request.decision == "CONFIRMED_APPLIED" else "NOT_SUBMITTED"
                    )
                    action.resolution_revision += 1
                    action.resolution_evidence = request.evidence
                    action.resolved_at = now
                    action.updated_at = now
                    audit_action(session, action, str(actor.user_id), "resolved")
            history = list((row.reconciliation or {}).get("history") or [])
            history.append(
                {
                    "decision": request.decision,
                    "evidence": request.evidence,
                    "platformItemId": request.platform_item_id,
                    "actorId": str(actor.user_id),
                    "occurredAt": now.isoformat(),
                    "attemptId": row.attempt_id,
                }
            )
            if request.decision == "KEEP_WAITING":
                row.business_state = "RECONCILING"
                row.stall_reason = "waiting for unique platform result"
                row.reconciliation = {"status": "KEEP_WAITING", "history": history}
                # A12 任务卡 #3: KEEP_WAITING 保留未决动作——台账行原样保留
                # （仍为 UNKNOWN、未决、继续阻断重领），只记录决策与审计。
                revision = _record_control_event(
                    row,
                    "RECONCILED_KEEP_WAITING",
                    request.evidence,
                    f"operator:{actor.user_id}",
                    now,
                )
                _audit_control_event(
                    session,
                    row,
                    action="reconciled_keep_waiting",
                    revision=revision,
                    actor_id=str(actor.user_id),
                    extra={"evidence": request.evidence[:160]},
                )
                return self._business_view(row)
            if request.decision == "CONFIRMED_APPLIED":
                if not request.platform_item_id:
                    raise ConflictError("CONFIRMED_APPLIED requires a unique platformItemId")
                row.status = "SUCCEEDED"
                row.business_state = "SUCCEEDED"
                row.error_code = None
                row.detail = request.evidence
                row.completed_at = now
                row.result = {
                    **dict(row.result or {}),
                    "outcome": "applied",
                    "platformItemId": request.platform_item_id,
                }
                row.reconciliation = {"status": "APPLIED", "history": history}
                revision = _record_control_event(
                    row,
                    "RECONCILED_APPLIED",
                    request.evidence,
                    f"operator:{actor.user_id}",
                    now,
                )
                _audit_control_event(
                    session,
                    row,
                    action="reconciled_applied",
                    revision=revision,
                    actor_id=str(actor.user_id),
                    extra={"platformItemId": request.platform_item_id},
                )
                await _settle_reply_delivery(session, row.id, "SUCCEEDED")
                return self._business_view(row)
            row.status = "FAILED"
            row.business_state = "FAILED"
            row.error_code = "CONFIRMED_NOT_SUBMITTED"
            row.detail = request.evidence
            row.completed_at = now
            row.reconciliation = {"status": "NOT_SUBMITTED", "history": history}
            revision = _record_control_event(
                row,
                "RECONCILED_NOT_SUBMITTED",
                request.evidence,
                f"operator:{actor.user_id}",
                now,
            )
            _audit_control_event(
                session,
                row,
                action="reconciled_not_submitted",
                revision=revision,
                actor_id=str(actor.user_id),
                extra={"evidence": request.evidence[:160]},
            )
            await _settle_reply_delivery(session, row.id, "FAILED")
            return self._business_view(row)

    async def pause(self, actor: Actor, task_id: str, reason: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_CONTROL)
        now = _now()
        async with self.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id, with_for_update=True)
            if row is None or row.tenant_id != str(actor.tenant_id):
                raise NotFoundError("platform task was not found")
            # A12: the decision is read from the explicit transition matrix.
            outcome = PAUSE_TRANSITIONS[_business_state_of(row)]
            if outcome == "IDEMPOTENT_RETURN":
                # Duplicate pause event: replay idempotently, no new revision.
                return self._business_view(row)
            if outcome == "REJECTED_TERMINAL":
                raise ConflictError("terminal platform task cannot be paused")
            if outcome == "REJECTED_RECONCILE_FIRST":
                raise ConflictError("uncertain result must be reconciled before pause")
            if outcome == "REJECTED_CANCEL_WINS":
                # A12 out-of-order protection: a cancel decision is sticky — a
                # late pause must not overwrite CANCEL_REQUESTED.
                raise ConflictError("cancelled task cannot be paused")
            revision = _record_control_event(
                row, "PAUSE_REQUESTED", reason, f"operator:{actor.user_id}", now
            )
            row.business_state = "PAUSE_REQUESTED"
            row.stall_reason = reason[:160]
            _audit_control_event(
                session,
                row,
                action="pause_requested",
                revision=revision,
                actor_id=str(actor.user_id),
            )
            return self._business_view(row)

    async def ack_paused(self, task_id: str, lease_id: str | None) -> dict[str, Any]:
        now = _now()
        async with self.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id, with_for_update=True)
            if row is None:
                raise NotFoundError("platform task was not found")
            # A12: the decision is read from the explicit transition matrix.
            outcome = ACK_PAUSED_TRANSITIONS[_business_state_of(row)]
            if outcome == "REJECTED_TERMINAL" or row.status in {"SUCCEEDED", "FAILED"}:
                raise ConflictError("terminal platform task cannot be pause-acked")
            if outcome == "REJECTED_RECONCILE_FIRST":
                raise ConflictError(
                    "uncertain result must be reconciled before pause acknowledgement"
                )
            if outcome == "REJECTED_CANCEL_WINS":
                raise ConflictError("cancelled task cannot be pause-acked")
            if outcome == "REJECTED_SUPERSEDED":
                # A12 out-of-order: resume already superseded the pause request;
                # a late ack must not drag the task back into a wait state.
                raise ConflictError(
                    "task already resumed; late pause acknowledgement is superseded"
                )
            if lease_id and row.lease_id and row.lease_id != lease_id:
                raise ConflictError("pause ack lease does not match")
            if outcome == "IDEMPOTENT_RETURN":
                # Duplicate ack (本地重复确认): replay idempotently — pause_ack_at
                # is not re-stamped and no new revision is minted.
                return self._business_view(row)
            if _has_commit_intent(row):
                row.business_state = "RECONCILING"
                row.stall_reason = row.stall_reason or "commit intent already written"
                kind = "PAUSE_ACKED_RECONCILING"
            else:
                row.business_state = "PAUSED_WAITING_USER"
                kind = "PAUSE_ACKED"
            row.pause_ack_at = now
            row.control_mode = "REMOTE"
            # A12 任务卡 #2: 本地按任务确认（pause ack）也是持久化控制事件。
            revision = _record_control_event(
                row, kind, row.stall_reason or "pause acknowledged", "companion", now
            )
            _audit_control_event(
                session,
                row,
                action="pause_acked",
                revision=revision,
                actor_id="companion",
                actor_type="companion",
            )
            return self._business_view(row)

    async def resume(
        self, actor: Actor, task_id: str, request: PlatformTaskResume
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_CONTROL)
        now = _now()
        async with self.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id, with_for_update=True)
            if row is None or row.tenant_id != str(actor.tenant_id):
                raise NotFoundError("platform task was not found")
            # A12: the state guard is read from the explicit transition matrix.
            outcome = RESUME_TRANSITIONS[_business_state_of(row)]
            if outcome == "REJECTED_CANCEL_WINS":
                raise ConflictError("cancelled task cannot be resumed")
            if outcome == "REJECTED_RECONCILE_FIRST":
                raise ConflictError("reconciling tasks must be decided before resume")
            if outcome != "RESUME_CHECK":
                raise ConflictError(
                    "resume requires pause ack before the original task can continue"
                )
            if not request.page_verified:
                # task-schedule/v1 fixture k03-positive-pause-resume: a resume
                # missing pageVerified is a request-level validation failure,
                # not a state conflict — the task itself is properly paused.
                raise ValidationError(
                    "resume requires pageVerified=true after resumeGuard",
                    fields={"pageVerified": "resume requires pageVerified=true after resumeGuard"},
                )
            if (row.command_payload or {}).get("commitIntent"):
                raise ConflictError("reconciling tasks must be decided before resume")
            live = None
            if row.account_id:
                live = await session.scalar(
                    select(AccountDeviceBindingRow).where(
                        AccountDeviceBindingRow.tenant_id == row.tenant_id,
                        AccountDeviceBindingRow.account_id == row.account_id,
                        AccountDeviceBindingRow.device_id == row.device_id,
                        AccountDeviceBindingRow.status == "BOUND",
                    )
                )
                if live is None or (
                    row.binding_version is not None and live.binding_version != row.binding_version
                ):
                    raise ConflictError("account or binding changed; original task cannot continue")
            device = await session.get(DeviceRow, row.device_id, with_for_update=True)
            if device is None or device.tenant_id != row.tenant_id:
                raise NotFoundError("device was not found")
            existing_lease = await session.get(DeviceLeaseRow, row.device_id, with_for_update=True)
            if existing_lease is not None:
                existing_lease.canceled_at = now
                await session.delete(existing_lease)
                await session.flush()
            device.fencing_counter = int(device.fencing_counter or 0) + 1
            device.control_epoch = int(getattr(device, "control_epoch", 0) or 0) + 1
            new_lease_id = str(uuid.uuid4())
            row.lease_id = new_lease_id
            row.lease_expires_at = now + timedelta(seconds=60)
            if row.status in {"QUEUED", "CLAIMED", "RUNNING"}:
                row.status = "RUNNING"
            row.business_state = "RESUME_CHECK"
            row.control_mode = "AUTO"
            row.resume_count = int(row.resume_count or 0) + 1
            row.stall_reason = request.reason
            session.add(
                DeviceLeaseRow(
                    device_id=device.id,
                    tenant_id=row.tenant_id,
                    lease_id=new_lease_id,
                    owner_workflow_id=f"auto/{row.id}",
                    fencing_token=device.fencing_counter,
                    expires_at=row.lease_expires_at,
                    canceled_at=None,
                    owner_type="AUTO",
                    created_at=now,
                )
            )
            if row.steps:
                metadata = dict(row.steps[0])
                metadata["controlEpoch"] = device.fencing_counter
                row.steps = [metadata, *row.steps[1:]]
            # A12: the resume decision (same taskId / frozen payload / recipe,
            # new epoch + lease) is a persisted control event with audit.
            revision = _record_control_event(
                row, "RESUMED", request.reason, f"operator:{actor.user_id}", now
            )
            _audit_control_event(
                session,
                row,
                action="resumed",
                revision=revision,
                actor_id=str(actor.user_id),
                extra={"pageVerified": True, "controlEpoch": device.fencing_counter},
            )
            return self._business_view(row)

    async def _stamp_business_fields(
        self,
        *,
        task_id: str,
        command_type: str,
        command_payload: dict[str, Any],
        batch_id: str,
        scheduled_for: datetime | None,
        operation_id: str | None = None,
    ) -> None:
        async with self.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id, with_for_update=True)
            if row is None:
                raise NotFoundError("platform task was not found")
            row.command_type = command_type
            row.operation_id = operation_id
            row.command_payload = command_payload
            row.business_state = "QUEUED"
            row.control_mode = "AUTO"
            row.batch_id = batch_id
            row.scheduled_for = scheduled_for
            row.attempt_id = row.attempt_id or str(uuid.uuid4())

    async def _freeze_publish_listing(
        self, actor: Actor, body: PlatformTaskCreate
    ) -> PlatformTaskCreate:
        if body.command_type != "xianyu.publish_listing.v1":
            return body
        product_id = body.product_id or body.parameters.get("productId")
        parameters = dict(body.parameters)
        media_delivery_id = body.media_delivery_id
        if isinstance(product_id, str) and product_id.strip():
            async with self.database.unit_of_work() as session:
                product = await session.scalar(
                    select(ProductRow).where(
                        ProductRow.id == product_id,
                        ProductRow.tenant_id == str(actor.tenant_id),
                    )
                )
                if product is None:
                    raise NotFoundError("product was not found")
                if product.status != "ACTIVE":
                    raise ConflictError("product is not active")
                media = list(
                    await session.scalars(
                        select(ProductMediaRow)
                        .where(
                            ProductMediaRow.product_id == product.id,
                            ProductMediaRow.tenant_id == str(actor.tenant_id),
                        )
                        .order_by(ProductMediaRow.sort_order)
                    )
                )
            if not media:
                raise ValidationError("product has no media assets for listing")
            parameters["listingBody"] = product.description
            parameters["price"] = str(product.price)
            parameters["mediaAssetIds"] = [row.media_asset_id for row in media]
            parameters["productId"] = product.id
            if not media_delivery_id:
                media_delivery_id = str(uuid.uuid4())
        media_ids = parameters.get("mediaAssetIds")
        if isinstance(media_ids, list) and media_ids and not media_delivery_id:
            media_delivery_id = str(uuid.uuid4())
        return body.model_copy(
            update={
                "parameters": parameters,
                "product_id": product_id if isinstance(product_id, str) else body.product_id,
                "media_delivery_id": media_delivery_id,
            }
        )

    def _mobile_body(self, device_id: str, body: PlatformTaskCreate) -> MobileTaskCreate:
        package = COMMAND_PACKAGES[body.command_type] or COMPANION_PACKAGE
        if body.command_type == "xianyu.publish_listing.v1":
            try:
                listing, price = listing_copy_from_parameters(body.parameters)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            media_ids = body.parameters.get("mediaAssetIds")
            raw = build_text_publish_task(
                device_id,
                description=listing,
                price=price,
                media_asset_ids=media_ids if isinstance(media_ids, list) and media_ids else None,
                delivery_id=body.media_delivery_id,
            )
        elif body.command_type == "xiaohongshu.publish_note.v1":
            raw = {
                "deviceId": device_id,
                "targetPackage": XHS_PACKAGE,
                "totalTimeoutMs": 30_000,
                "steps": _xhs_note_steps(),
            }
        elif body.command_type == "xianyu.collect_orders.v1":
            raw = {
                "deviceId": device_id,
                "targetPackage": XIANYU_PACKAGE,
                "totalTimeoutMs": 30_000,
                "steps": [
                    {
                        "stepId": "mark-collect-frozen",
                        "action": "run.log",
                        "level": "INFO",
                        "messageCode": "XIANYU_COLLECT_ORDERS_FROZEN",
                        "timeoutMs": 1_000,
                    }
                ],
            }
        else:
            raw = {
                "deviceId": device_id,
                "targetPackage": package,
                "totalTimeoutMs": 30_000,
                "steps": _probe_steps(),
            }
        raw["accountId"] = body.account_id
        if body.expected_binding_version is not None:
            raw["expectedBindingVersion"] = body.expected_binding_version
        return MobileTaskCreate.model_validate(raw)

    @staticmethod
    def _business_view(row: MobileTaskRow) -> dict[str, Any]:
        business = row.business_state or RUNNER_TO_BUSINESS.get(row.status, row.status)
        if business == "CANCELED":
            business = "CANCELLED"
        control_revision, control_events = _control_view(row)
        return {
            "id": row.id,
            "taskId": row.id,
            "deviceId": row.device_id,
            "accountId": row.account_id,
            "bindingVersion": row.binding_version,
            "deviceIdAtExecution": row.device_id_at_execution,
            "commandType": row.command_type,
            "operationId": row.operation_id,
            "commandPayload": row.command_payload,
            "snapshotSha256": (row.command_payload or {}).get("snapshotSha256"),
            "state": business,
            "runnerStatus": row.status,
            "controlMode": row.control_mode or "AUTO",
            "batchId": row.batch_id,
            "attempt": row.attempt,
            "attemptId": row.attempt_id,
            "scheduledFor": row.scheduled_for,
            "stallReason": row.stall_reason,
            "resumeCount": row.resume_count,
            "controlEpoch": ((row.steps or [{}])[0] or {}).get("controlEpoch"),
            "controlRevision": control_revision,
            "controlEvents": control_events,
            "pauseAckAt": row.pause_ack_at,
            "reconciliation": row.reconciliation,
            "errorCode": row.error_code,
            "detail": row.detail,
            "result": row.result,
            "createdBy": row.requested_by,
            "createdAt": row.created_at,
            "startedAt": row.started_at,
            "completedAt": row.completed_at,
        }

    @staticmethod
    def _event_view(row: MobileTaskEventRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "taskId": row.task_id,
            "attemptId": row.attempt_id,
            "sequence": row.sequence,
            "eventType": row.event_type,
            "stepIndex": row.step_index,
            "stepId": row.step_id,
            "payload": row.payload,
            "occurredAt": row.occurred_at,
            "receivedAt": row.received_at,
        }
