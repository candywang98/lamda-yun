"""Business PlatformTask facade over MobileTask. Does not create a second queue."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from cloudctl_domain import Actor, ConflictError, NotFoundError, Permission, ValidationError, require_permissions
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from .builtin_recipes import builtin_recipe_ref
from .command_factory import mint_operation_command
from .command_v1 import COMMAND_PACKAGES, CommandType
from .db import (
    AccountDeviceBindingRow,
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
from .mobile_service import COMPANION_PACKAGE, XIANYU_PACKAGE, MobileTaskService
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
            raise ValueError("decision must be CONFIRMED_APPLIED, CONFIRMED_NOT_SUBMITTED, or KEEP_WAITING")
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
                    statement.order_by(MobileTaskRow.created_at.desc(), MobileTaskRow.id.desc()).limit(
                        limit + 1
                    )
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
            current = row.business_state or RUNNER_TO_BUSINESS.get(row.status, row.status)
            if current in TERMINAL_BUSINESS:
                if current == "CANCELLED":
                    return self._business_view(row)
                raise ConflictError("terminal platform task cannot be canceled")
            if current == "RECONCILING":
                raise ConflictError("uncertain result must be reconciled before cancellation")
            if current in {"QUEUED", "WAITING_MATERIALS", "PREFLIGHT", "PAUSE_REQUESTED", "PAUSED_WAITING_USER"}:
                row.status = "FAILED"
                row.business_state = "CANCELLED"
                row.error_code = "CANCELLED"
                row.detail = reason
                row.completed_at = now
                row.lease_id = None
                row.lease_expires_at = None
                await _settle_reply_delivery(session, row.id, "CANCELLED")
            else:
                row.business_state = "CANCEL_REQUESTED"
                row.stall_reason = reason
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
                raise ConflictError("uncertain or binding-changed failures must be reconciled first")
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
        async with self.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id, with_for_update=True)
            if row is None or row.tenant_id != str(actor.tenant_id):
                raise NotFoundError("platform task was not found")
            current = row.business_state or RUNNER_TO_BUSINESS.get(row.status, row.status)
            if current in TERMINAL_BUSINESS or row.status == "SUCCEEDED":
                raise ConflictError("terminal tasks cannot enter reconciliation")
            row.business_state = "RECONCILING"
            row.stall_reason = reason
            row.reconciliation = {
                **dict(row.reconciliation or {}),
                "status": "UNKNOWN",
                "reason": reason,
                "history": list((row.reconciliation or {}).get("history") or []),
            }
            return self._business_view(row)

    async def reconcile(self, actor: Actor, task_id: str, request: PlatformTaskReconcile) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.TASK_CREATE)
        now = _now()
        async with self.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id, with_for_update=True)
            if row is None or row.tenant_id != str(actor.tenant_id):
                raise NotFoundError("platform task was not found")
            if row.business_state in TERMINAL_BUSINESS:
                raise ConflictError("terminal tasks cannot be reconciled again")
            if row.business_state != "RECONCILING" and row.error_code not in {"COMMIT_UNKNOWN", "RECONCILING"}:
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
                await _settle_reply_delivery(session, row.id, "SUCCEEDED")
                return self._business_view(row)
            row.status = "FAILED"
            row.business_state = "FAILED"
            row.error_code = "CONFIRMED_NOT_SUBMITTED"
            row.detail = request.evidence
            row.completed_at = now
            row.reconciliation = {"status": "NOT_SUBMITTED", "history": history}
            await _settle_reply_delivery(session, row.id, "FAILED")
            return self._business_view(row)

    async def pause(self, actor: Actor, task_id: str, reason: str) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_CONTROL)
        async with self.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id, with_for_update=True)
            if row is None or row.tenant_id != str(actor.tenant_id):
                raise NotFoundError("platform task was not found")
            current = row.business_state or RUNNER_TO_BUSINESS.get(row.status, row.status)
            if current in TERMINAL_BUSINESS:
                raise ConflictError("terminal platform task cannot be paused")
            if current == "RECONCILING":
                raise ConflictError("uncertain result must be reconciled before pause")
            if current == "PAUSED_WAITING_USER":
                return self._business_view(row)
            row.business_state = "PAUSE_REQUESTED"
            row.stall_reason = reason
            return self._business_view(row)

    async def ack_paused(self, task_id: str, lease_id: str | None) -> dict[str, Any]:
        now = _now()
        async with self.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id, with_for_update=True)
            if row is None:
                raise NotFoundError("platform task was not found")
            current = row.business_state or RUNNER_TO_BUSINESS.get(row.status, row.status)
            if current in TERMINAL_BUSINESS or row.status in {"SUCCEEDED", "FAILED"}:
                raise ConflictError("terminal platform task cannot be pause-acked")
            if current == "RECONCILING":
                raise ConflictError("uncertain result must be reconciled before pause acknowledgement")
            if current in {"CANCEL_REQUESTED"}:
                raise ConflictError("cancelled task cannot be pause-acked")
            if lease_id and row.lease_id and row.lease_id != lease_id:
                raise ConflictError("pause ack lease does not match")
            if (row.command_payload or {}).get("commitIntent"):
                row.business_state = "RECONCILING"
                row.stall_reason = "commit intent already written"
            else:
                row.business_state = "PAUSED_WAITING_USER"
            row.pause_ack_at = now
            row.control_mode = "REMOTE"
            return self._business_view(row)

    async def resume(self, actor: Actor, task_id: str, request: PlatformTaskResume) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_CONTROL)
        now = _now()
        async with self.database.unit_of_work() as session:
            row = await session.get(MobileTaskRow, task_id, with_for_update=True)
            if row is None or row.tenant_id != str(actor.tenant_id):
                raise NotFoundError("platform task was not found")
            if row.business_state in {"CANCELLED", "CANCEL_REQUESTED"}:
                raise ConflictError("cancelled task cannot be resumed")
            if row.business_state == "RECONCILING":
                raise ConflictError("reconciling tasks must be decided before resume")
            if row.business_state != "PAUSED_WAITING_USER":
                raise ConflictError("resume requires pause ack before the original task can continue")
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
                auto_publish=True,
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
