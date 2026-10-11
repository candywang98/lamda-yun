"""Explicit, lease-fenced single-screen IM collection; no notification writes."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from cloudctl_domain import ConflictError, NotFoundError, Permission, require_permissions
from pydantic import ValidationError as SchemaError
from sqlalchemy import select

from .db import DeviceLeaseRow, DeviceRow, ImThreadRow, MobileBindingRow, MobileTaskRow
from .fleet_identity import (
    active_session,
    device_online,
    evaluate_executable,
    negotiated_engine_min,
)
from .mobile_schemas import CollectImChatStep, ImChatCompletion, ImChatTarget, MobileTaskCreate

PROTOCOL = "im-chat-collection/1"
ACTION = "ui.collectImChat"
CAPABILITY = "imChatCollectionProtocol"


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def is_collection(row: MobileTaskRow) -> bool:
    return any(step.get("action") == ACTION for step in row.steps)


def frozen_target(row: MobileTaskRow) -> ImChatTarget:
    if len(row.steps) != 2 or row.target_package != "com.taobao.idlefish":
        raise ConflictError("IM_COLLECTION_SHAPE_INVALID")
    try:
        body = MobileTaskCreate.model_validate(
            {
                "deviceId": row.device_id,
                "targetPackage": row.target_package,
                "totalTimeoutMs": row.steps[0].get("totalTimeoutMs"),
                "steps": row.steps[1:],
            }
        )
    except SchemaError as exc:
        raise ConflictError("IM_COLLECTION_SHAPE_INVALID") from exc
    step = body.steps[0]
    if not isinstance(step, CollectImChatStep) or row.account_id is not None:
        raise ConflictError("IM_COLLECTION_SHAPE_INVALID")
    digest = hashlib.sha256(
        canonical(body.model_dump(mode="json", by_alias=True, exclude_none=True)).encode()
    ).hexdigest()
    if digest != row.request_sha256:
        raise ConflictError("IM_COLLECTION_TARGET_CHANGED")
    return step.target


async def capability(session: Any, device: DeviceRow | None, now: datetime) -> dict[str, Any]:
    supported = False
    reason = "IM_COLLECTION_NO_BINDING"
    if device is not None and device.active_binding_id:
        binding = await session.get(MobileBindingRow, device.active_binding_id)
        if (
            binding is not None
            and binding.revoked_at is None
            and binding.device_id == device.id
            and binding.tenant_id == device.tenant_id
        ):
            supported = (device.capabilities or {}).get(CAPABILITY) == PROTOCOL and (
                device.capabilities or {}
            ).get("imChatCollectionBindingId") == binding.id
            reason = "IM_COLLECTION_UNSUPPORTED"
            if supported:
                reason = "IM_COLLECTION_OFFLINE"
                if device_online(device.last_seen_at, now):
                    reason = "IM_COLLECTION_NOT_EXECUTABLE"
                    fleet = await active_session(session, device.tenant_id, binding.id)
                    executable = bool((device.capabilities or {}).get("accessibilityEnabled"))
                    if fleet is not None:
                        executable, _, _ = evaluate_executable(
                            online=True,
                            accessibility_enabled=fleet.accessibility_enabled,
                            accessibility_active=fleet.accessibility_active,
                            ime_ready=fleet.ime_ready,
                            screen_unlocked=fleet.screen_unlocked,
                            engine_version=fleet.engine_version,
                            engine_min=negotiated_engine_min(fleet.capabilities),
                        )
                    if executable and not device.maintenance:
                        return {"supported": True, "available": True, "reason": None}
    return {"supported": supported, "available": False, "reason": reason}


async def validate_target(
    session: Any,
    tenant_id: str,
    device: DeviceRow,
    target: ImChatTarget,
    *,
    require_available: bool,
) -> None:
    thread = await session.get(ImThreadRow, target.thread_id, populate_existing=True)
    binding = await session.get(MobileBindingRow, target.mobile_binding_id)
    if (
        thread is None
        or thread.tenant_id != tenant_id
        or target.tenant_id != tenant_id
        or device.tenant_id != tenant_id
        or target.device_id != device.id
        or thread.device_id != device.id
        or target.platform != thread.platform
        or target.peer_key != thread.peer_key
        or target.peer_name != thread.peer_name
        or device.active_binding_id != target.mobile_binding_id
        or binding is None
        or binding.revoked_at is not None
        or binding.tenant_id != tenant_id
        or binding.device_id != device.id
    ):
        raise ConflictError("IM_COLLECTION_TARGET_MISMATCH")
    if require_available:
        state = await capability(session, device, datetime.now(UTC))
        if not state["available"]:
            raise ConflictError(state["reason"])


async def create(im: Any, actor: Any, thread_id: str, key: str) -> tuple[dict[str, Any], bool]:
    require_permissions(actor.roles, Permission.DEVICE_CONTROL)
    async with im.database.unit_of_work() as session:
        thread = await session.get(ImThreadRow, thread_id)
        if thread is None or thread.tenant_id != str(actor.tenant_id):
            raise NotFoundError("thread was not found")
        device = await session.get(DeviceRow, thread.device_id)
        if device is None or not device.active_binding_id:
            raise ConflictError("IM_COLLECTION_NO_BINDING")
        target = ImChatTarget.model_validate(
            {
                "protocolVersion": PROTOCOL,
                "tenantId": thread.tenant_id,
                "deviceId": thread.device_id,
                "threadId": thread.id,
                "platform": thread.platform,
                "peerKey": thread.peer_key,
                "peerName": thread.peer_name,
                "mobileBindingId": device.active_binding_id,
                "scope": "VISIBLE_SCREEN",
                "noSend": True,
            }
        )
        body = MobileTaskCreate.model_validate(
            {
                "deviceId": device.id,
                "targetPackage": "com.taobao.idlefish",
                "totalTimeoutMs": 60000,
                "steps": [
                    {
                        "stepId": "collect-im-chat",
                        "action": ACTION,
                        "timeoutMs": 60000,
                        "target": target.model_dump(by_alias=True),
                    }
                ],
            }
        )
    view, created = await im.mobile._insert_task(
        tenant_id=str(actor.tenant_id),
        requested_by=str(actor.user_id),
        key=key,
        body=body,
    )
    return {
        "taskId": view["id"],
        "threadId": target.thread_id,
        "status": view["businessState"],
    }, created


async def list_collections(im: Any, actor: Any, thread_id: str) -> dict[str, Any]:
    require_permissions(actor.roles, Permission.DEVICE_READ)
    async with im.database.unit_of_work() as session:
        thread = await im._owned_thread(session, actor, thread_id)
        device = await session.get(DeviceRow, thread.device_id)
        rows = await session.scalars(
            select(MobileTaskRow)
            .where(
                MobileTaskRow.tenant_id == thread.tenant_id,
                MobileTaskRow.device_id == thread.device_id,
                MobileTaskRow.steps[1]["action"].as_string() == ACTION,
                MobileTaskRow.steps[1]["target"]["threadId"].as_string() == thread.id,
            )
            .order_by(MobileTaskRow.created_at.desc(), MobileTaskRow.id.desc())
            .limit(10)
        )
        return {
            "capability": await capability(session, device, datetime.now(UTC)),
            "items": [
                {
                    "taskId": row.id,
                    "threadId": thread.id,
                    "status": row.business_state,
                    "createdAt": row.created_at,
                    "errorCode": row.error_code,
                    "snapshot": row.result.get("snapshot")
                    if row.business_state == "SUCCEEDED"
                    else None,
                }
                for row in rows
            ],
        }


async def complete(
    im: Any, binding: MobileBindingRow, task_id: str, body: ImChatCompletion
) -> dict[str, Any]:
    now = datetime.now(UTC)
    wire = body.model_dump(mode="json", by_alias=True)
    digest = hashlib.sha256(canonical(wire).encode()).hexdigest()
    async with im.database.unit_of_work() as session:
        # Same device -> task -> lease ordering as the task claim path.
        device = await session.get(DeviceRow, binding.device_id, with_for_update=True)
        row = await session.get(MobileTaskRow, task_id, with_for_update=True)
        im.mobile._validate_owned_task(row, binding)
        if device is None or row is None:
            raise NotFoundError("mobile task was not found")
        target = frozen_target(row)
        await validate_target(session, binding.tenant_id, device, target, require_available=False)
        if target != body.target or target.mobile_binding_id != binding.id:
            raise ConflictError("IM_COLLECTION_TARGET_MISMATCH")
        if body.snapshot.peer_identity.observed_name.strip() != target.peer_name:
            raise ConflictError("IM_COLLECTION_PEER_MISMATCH")
        if row.business_state == "SUCCEEDED":
            if row.result.get("completionHash") == digest:
                return {"taskId": row.id, "threadId": target.thread_id, "status": "SUCCEEDED"}
            raise ConflictError("IM_COLLECTION_COMPLETION_CONFLICT")
        if row.business_state not in {"PREFLIGHT", "RUNNING"}:
            raise ConflictError("IM_COLLECTION_NOT_RUNNING")
        im.mobile._validate_active_lease(row, body.lease_id)
        lease = await session.get(DeviceLeaseRow, binding.device_id, with_for_update=True)
        if (
            lease is None
            or lease.lease_id != body.lease_id
            or lease.canceled_at is not None
            or lease.tenant_id != binding.tenant_id
            or lease.owner_type != "AUTO"
            or lease.owner_workflow_id != f"auto/{row.id}"
            or lease.fencing_token != body.control_epoch
            or row.steps[0].get("controlEpoch") != body.control_epoch
            or lease.expires_at.replace(tzinfo=UTC) <= now
        ):
            raise ConflictError("IM_COLLECTION_LEASE_MISMATCH")
        row.result = {
            "protocolVersion": PROTOCOL,
            "snapshot": wire["snapshot"],
            "target": wire["target"],
            "completionHash": digest,
            "leaseId": body.lease_id,
            "controlEpoch": body.control_epoch,
        }
        row.status = row.business_state = "SUCCEEDED"
        row.completed_at, row.lease_expires_at = now, None
        lease.canceled_at = now
        return {"taskId": row.id, "threadId": target.thread_id, "status": "SUCCEEDED"}
