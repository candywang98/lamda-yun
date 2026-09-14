"""IM aggregation slice 1: companion push, operator threads, gated reply tasks.

Contract: contracts/phase1/pa-im-aggregation-v1.md (pa-im/20260913.1).
Replies are ordinary allowlisted steps tasks; no new gate type is introduced.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from cloudctl_domain import ConflictError, NotFoundError
from sqlalchemy import select

from .db import ImMessageRow, ImMonitorConfigRow, ImThreadRow, MobileTaskRow
from .mobile_schemas import MobileTaskCreate
from .mobile_service import MobileTaskService, _now

PLATFORM = "xianyu"
MAX_BATCH = 20
MAX_TEXT = 2_000
MAX_REPLY = 500
REPLY_COOLDOWN = timedelta(seconds=60)

REPLY_STEPS_PACKAGE = "com.taobao.idlefish"


def _dedupe_key(device_id: str, peer_key: str, occurred_at: datetime, text: str) -> str:
    bucket = int(occurred_at.timestamp())
    raw = f"{device_id}|{peer_key}|{bucket}|{text}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _thread_view(row: ImThreadRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "deviceId": row.device_id,
        "platform": row.platform,
        "peerKey": row.peer_key,
        "peerName": row.peer_name,
        "lastMessageAt": row.last_message_at,
        "lastDirection": row.last_direction,
        "unreadCount": row.unread_count,
    }


def _message_view(row: ImMessageRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "threadId": row.thread_id,
        "direction": row.direction,
        "contentType": row.content_type,
        "text": row.text_content,
        "occurredAt": row.occurred_at,
        "replyTaskId": row.reply_task_id,
    }


class ImService:
    def __init__(self, mobile: MobileTaskService) -> None:
        self.mobile = mobile
        self.database = mobile.database


    ALLOWED_PLATFORMS = {"xianyu", "xhs", "douyin", "wechat"}

    async def get_config(self, actor: Any, device_id: str) -> dict[str, Any]:
        async with self.database.unit_of_work() as session:
            row = await session.get(ImMonitorConfigRow, device_id)
            if row is not None and row.tenant_id != str(actor.tenant_id):
                raise NotFoundError("device was not found")
            return self._config_view(row, device_id)

    async def companion_config(self, binding_row: Any) -> dict[str, Any]:
        async with self.database.unit_of_work() as session:
            row = await session.get(ImMonitorConfigRow, binding_row.device_id)
            return self._config_view(row, binding_row.device_id)

    async def upsert_config(self, actor: Any, device_id: str, body: dict[str, Any]) -> dict[str, Any]:
        platforms = body.get("platforms") or ["xianyu"]
        if not isinstance(platforms, list) or not platforms:
            raise ConflictError("platforms must be a non-empty list")
        if len(platforms) > len(self.ALLOWED_PLATFORMS) or any(
            item not in self.ALLOWED_PLATFORMS for item in platforms
        ):
            raise ConflictError("platforms contains an unsupported value")
        mode = body.get("mode", "NOTIFICATION")
        if mode not in ("NOTIFICATION", "DUTY"):
            raise ConflictError("mode is invalid")
        duty_start = self._validate_clock(body.get("dutyStart", "09:00"))
        duty_end = self._validate_clock(body.get("dutyEnd", "23:00"))
        enabled = bool(body.get("enabled", True))
        now = _now()
        async with self.database.unit_of_work() as session:
            from .db import DeviceRow

            found = await session.get(DeviceRow, device_id)
            if found is None or found.tenant_id != str(actor.tenant_id):
                raise NotFoundError("device was not found")
            row = await session.get(ImMonitorConfigRow, device_id, with_for_update=True)
            if row is None:
                row = ImMonitorConfigRow(
                    device_id=device_id, tenant_id=str(actor.tenant_id), platforms=platforms,
                    mode=mode, duty_start=duty_start, duty_end=duty_end, enabled=enabled,
                    updated_at=now, updated_by=str(actor.user_id),
                )
                session.add(row)
            else:
                row.platforms = platforms
                row.mode = mode
                row.duty_start = duty_start
                row.duty_end = duty_end
                row.enabled = enabled
                row.updated_at = now
                row.updated_by = str(actor.user_id)
            return self._config_view(row, device_id)

    @staticmethod
    def _validate_clock(value: str) -> str:
        import re as _re

        if not _re.fullmatch(r"[0-2][0-9]:[0-5][0-9]", value or ""):
            raise ConflictError("duty window is invalid")
        return value

    @staticmethod
    def _config_view(row, device_id: str) -> dict[str, Any]:
        if row is None:
            return {"deviceId": device_id, "enabled": True, "platforms": ["xianyu"],
                    "mode": "NOTIFICATION", "dutyStart": "09:00", "dutyEnd": "23:00", "updatedAt": None}
        return {"deviceId": row.device_id, "enabled": row.enabled, "platforms": row.platforms,
                "mode": row.mode, "dutyStart": row.duty_start, "dutyEnd": row.duty_end,
                "updatedAt": row.updated_at}

    async def ingest(self, binding_row: Any, items: list[dict[str, Any]]) -> dict[str, int]:
        if not 1 <= len(items) <= MAX_BATCH:
            raise ConflictError(f"batch must contain 1..{MAX_BATCH} messages")
        now = _now()
        accepted = 0
        duplicates = 0
        async with self.database.unit_of_work() as session:
            for item in items:
                peer_key = item["peerKey"].strip()
                peer_name = item["peerName"].strip()
                text = item["text"]
                if not peer_key or len(peer_key) > 128 or not peer_name or len(peer_name) > 128:
                    raise ConflictError("peer identity is invalid")
                if not text or not text.strip():
                    continue
                truncated = False
                if len(text) > MAX_TEXT:
                    text = text[:MAX_TEXT]
                    truncated = True
                if truncated:
                    text = "TRUNCATED " + text
                occurred = item["occurredAt"]
                if occurred.tzinfo is None:
                    occurred = occurred.replace(tzinfo=UTC)
                key = _dedupe_key(binding_row.device_id, peer_key, occurred, text)
                existing = await session.scalar(
                    select(ImMessageRow).where(ImMessageRow.dedupe_key == key)
                )
                if existing is not None:
                    duplicates += 1
                    continue
                thread = await session.scalar(
                    select(ImThreadRow)
                    .where(
                        ImThreadRow.tenant_id == binding_row.tenant_id,
                        ImThreadRow.device_id == binding_row.device_id,
                        ImThreadRow.peer_key == peer_key,
                    )
                    .with_for_update()
                )
                if thread is None:
                    thread = ImThreadRow(
                        id=str(uuid.uuid4()),
                        tenant_id=binding_row.tenant_id,
                        device_id=binding_row.device_id,
                        platform=PLATFORM,
                        peer_key=peer_key,
                        peer_name=peer_name,
                        last_message_at=occurred,
                        last_direction="IN",
                        unread_count=0,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(thread)
                    await session.flush()
                session.add(
                    ImMessageRow(
                        id=str(uuid.uuid4()),
                        tenant_id=binding_row.tenant_id,
                        thread_id=thread.id,
                        direction="IN",
                        content_type="TEXT",
                        text_content=text,
                        occurred_at=occurred,
                        dedupe_key=key,
                        created_at=now,
                    )
                )
                thread.peer_name = peer_name
                thread.last_message_at = occurred
                thread.last_direction = "IN"
                thread.unread_count += 1
                thread.updated_at = now
                accepted += 1
        return {"accepted": accepted, "duplicates": duplicates}

    async def list_threads(
        self,
        actor: Any,
        device_id: str | None,
        unread_only: bool,
        after: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        async with self.database.unit_of_work() as session:
            query = select(ImThreadRow).where(ImThreadRow.tenant_id == str(actor.tenant_id))
            if device_id:
                query = query.where(ImThreadRow.device_id == device_id)
            if unread_only:
                query = query.where(ImThreadRow.unread_count > 0)
            if after:
                anchor = await session.get(ImThreadRow, after)
                if anchor is None or anchor.tenant_id != str(actor.tenant_id):
                    raise NotFoundError("thread was not found")
                query = query.where(ImThreadRow.last_message_at < anchor.last_message_at)
            rows = await session.scalars(
                query.order_by(ImThreadRow.last_message_at.desc()).limit(limit)
            )
            return [_thread_view(row) for row in rows]

    async def _owned_thread(self, session: Any, actor: Any, thread_id: str) -> ImThreadRow:
        row = await session.get(ImThreadRow, thread_id, with_for_update=True)
        if row is None or row.tenant_id != str(actor.tenant_id):
            raise NotFoundError("thread was not found")
        return row

    async def list_messages(
        self, actor: Any, thread_id: str, after: str | None, limit: int
    ) -> list[dict[str, Any]]:
        async with self.database.unit_of_work() as session:
            thread = await self._owned_thread(session, actor, thread_id)
            query = select(ImMessageRow).where(ImMessageRow.thread_id == thread.id)
            if after:
                anchor = await session.get(ImMessageRow, after)
                if anchor is None or anchor.thread_id != thread.id:
                    raise NotFoundError("message was not found")
                query = query.where(ImMessageRow.occurred_at >= anchor.occurred_at)
            rows = await session.scalars(query.order_by(ImMessageRow.occurred_at.asc()).limit(limit))
            return [_message_view(row) for row in rows]

    async def mark_read(self, actor: Any, thread_id: str) -> dict[str, Any]:
        async with self.database.unit_of_work() as session:
            thread = await self._owned_thread(session, actor, thread_id)
            thread.unread_count = 0
            thread.updated_at = _now()
            return _thread_view(thread)

    async def reply(self, actor: Any, thread_id: str, text: str) -> dict[str, Any]:
        text = text.strip()
        if not text or len(text) > MAX_REPLY:
            raise ConflictError(f"reply text must be 1..{MAX_REPLY} characters")
        now = _now()
        async with self.database.unit_of_work() as session:
            thread = await self._owned_thread(session, actor, thread_id)
            recent = await session.scalar(
                select(ImMessageRow)
                .where(
                    ImMessageRow.thread_id == thread.id,
                    ImMessageRow.direction == "OUT",
                    ImMessageRow.occurred_at > now - REPLY_COOLDOWN,
                )
                .order_by(ImMessageRow.occurred_at.desc())
            )
            if recent is not None:
                raise ConflictError("THREAD_REPLY_RATE_LIMITED")
            busy = await session.scalar(
                select(MobileTaskRow.id).where(
                    MobileTaskRow.device_id == thread.device_id,
                    MobileTaskRow.business_state.in_(["RUNNING", "RECONCILING"]),
                )
            )
            if busy is not None:
                raise ConflictError("DEVICE_BUSY")
            last_in = await session.scalar(
                select(ImMessageRow)
                .where(ImMessageRow.thread_id == thread.id, ImMessageRow.direction == "IN")
                .order_by(ImMessageRow.occurred_at.desc())
            )
            if last_in is None:
                raise ConflictError("THREAD_HAS_NO_INBOUND")
            body = MobileTaskCreate.model_validate(
                {
                    "deviceId": thread.device_id,
                    "targetPackage": REPLY_STEPS_PACKAGE,
                    "totalTimeoutMs": 120_000,
                    "steps": _reply_steps(thread.peer_name, text),
                }
            )
            from sqlalchemy import func as sa_func

            reply_ordinal = await session.scalar(
                select(sa_func.count()).select_from(ImMessageRow).where(
                    ImMessageRow.thread_id == thread.id,
                    ImMessageRow.direction == "OUT",
                )
            ) or 0
            task_view, created = await self.mobile.create_task(
                actor, f"im-reply:{thread.id}:{last_in.id}:{reply_ordinal}", body
            )
            if not created:
                # Idempotent replay: the task (and its OUT message) already exist.
                return {"taskId": task_view["id"], "threadId": thread.id}
            session.add(
                ImMessageRow(
                    id=str(uuid.uuid4()),
                    tenant_id=thread.tenant_id,
                    thread_id=thread.id,
                    direction="OUT",
                    content_type="TEXT",
                    text_content=text,
                    occurred_at=now,
                    dedupe_key=hashlib.sha256(f"out|{task_view['id']}".encode()).hexdigest(),
                    reply_task_id=task_view["id"],
                    created_at=now,
                )
            )
            thread.last_message_at = now
            thread.last_direction = "OUT"
            thread.updated_at = now
            return {"taskId": task_view["id"], "threadId": thread.id}


def _reply_steps(peer_name: str, text: str) -> list[dict[str, Any]]:
    return [
        {"stepId": "find-messages-tab", "locatorRef": "xianyu_messages_tab", "timeoutMs": 8000,
         "action": "ui.find"},
        {"stepId": "open-messages-tab", "locatorRef": "xianyu_messages_tab", "timeoutMs": 8000,
         "action": "ui.tap"},
        {"stepId": "open-conversation", "timeoutMs": 8000, "action": "ui.tapText",
         "value": peer_name[:64]},
        {"stepId": "wait-chat-input", "locatorRef": "xianyu_chat_input", "timeoutMs": 8000,
         "action": "ui.wait", "condition": "EXISTS", "pollMs": 200},
        {"stepId": "fill-reply", "locatorRef": "xianyu_chat_input", "timeoutMs": 20000,
         "action": "ui.input", "value": text, "replace": True, "sensitive": False},
        {"stepId": "send-reply", "locatorRef": "xianyu_chat_send", "timeoutMs": 8000,
         "action": "ui.tap"},
    ]
