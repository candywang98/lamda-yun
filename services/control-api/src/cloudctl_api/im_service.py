"""IM aggregation slice 1: companion push, operator threads, gated reply tasks.

Contract: contracts/phase1/pa-im-aggregation-v1.md (pa-im/20260913.1).
Replies are ordinary allowlisted steps tasks; no new gate type is introduced.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from cloudctl_domain import ConflictError, NotFoundError, Permission, require_permissions
from sqlalchemy import and_, func, or_, select

from .db import (
    AuditEventRow,
    ImClassificationRow,
    ImMessageRow,
    ImMonitorConfigRow,
    ImThreadRow,
    MobileTaskRow,
)
from .im_classification import (
    bucket_predicate,
    classification_view,
    new_classification,
    notification_rule,
    persist_assessment,
)
from .im_classifier import MessageAssessment
from .im_observer import ImClassificationObserver, InboundObservation
from .mobile_schemas import MobileTaskCreate
from .mobile_service import MobileTaskService, _now

PLATFORM = "xianyu"
MAX_BATCH = 20
MAX_TEXT = 2_000
TRANSPORT_TEXT_LIMIT = 4_000
TRUNCATED_PREFIX = "TRUNCATED "
MAX_REPLY = 500
REPLY_COOLDOWN = timedelta(seconds=60)

REPLY_STEPS_PACKAGE = "com.taobao.idlefish"

# Terminal business state -> delivery state of the OUT message bound to the task.
# DELIVERED is absorbing: once a reply is confirmed delivered it is never
# downgraded, so a late/duplicated failure report cannot retract a sent message.
TASK_TERMINAL_DELIVERY = {
    "SUCCEEDED": "DELIVERED",
    "FAILED": "FAILED",
    "CANCELLED": "FAILED",
    "CANCELED": "FAILED",
    "EXPIRED": "FAILED",
}


async def settle_reply_delivery(session: Any, task_id: str, business_state: str) -> None:
    """Idempotently settle the OUT im_message bound to a terminal reply task.

    Called from every server-side path that writes a terminal task state
    (companion complete/fail, operator cancel, reconciliation). Repeated reports
    of the same terminal state are no-ops; a FAILED/CANCELLED/EXPIRED report
    never overwrites DELIVERED.
    """
    target = TASK_TERMINAL_DELIVERY.get(business_state)
    if target is None:
        return
    rows = list(
        await session.scalars(
            select(ImMessageRow).where(ImMessageRow.reply_task_id == task_id).with_for_update()
        )
    )
    for row in rows:
        if row.delivery_state == "DELIVERED":
            continue
        row.delivery_state = target


def canonical_text(raw: str) -> str:
    """Mirror Android ImCanonicalText using Python Unicode code points."""
    body = raw[:TRANSPORT_TEXT_LIMIT]
    if len(body) <= MAX_TEXT:
        return body
    if body.startswith(TRUNCATED_PREFIX) and len(body.removeprefix(TRUNCATED_PREFIX)) == MAX_TEXT:
        return body
    return TRUNCATED_PREFIX + body[:MAX_TEXT]


def _dedupe_key(
    device_id: str,
    platform: str,
    peer_key: str,
    occurred_at: datetime,
    text: str,
) -> str:
    bucket = int(occurred_at.timestamp())
    raw = f"{device_id}|{platform}|{peer_key}|{bucket}|{canonical_text(text)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _thread_view(row: ImThreadRow, last_message_text: str | None = None) -> dict[str, Any]:
    return {
        "id": row.id,
        "deviceId": row.device_id,
        "platform": row.platform,
        "peerKey": row.peer_key,
        "peerName": row.peer_name,
        "lastMessageAt": row.last_message_at.replace(tzinfo=UTC)
        if row.last_message_at.tzinfo is None
        else row.last_message_at,
        "lastDirection": row.last_direction,
        "lastMessageText": last_message_text,
        "lastMessageClassification": None,
        "unreadCount": row.unread_count,
    }


def _message_view(
    row: ImMessageRow,
    classification: ImClassificationRow | None = None,
) -> dict[str, Any]:
    return {
        "id": row.id,
        "threadId": row.thread_id,
        "direction": row.direction,
        "contentType": row.content_type,
        "text": row.text_content,
        "occurredAt": row.occurred_at.replace(tzinfo=UTC)
        if row.occurred_at.tzinfo is None
        else row.occurred_at,
        "replyTaskId": row.reply_task_id,
        "deliveryState": row.delivery_state,
        "classification": classification_view(classification) if row.direction == "IN" else None,
        "notificationMetadata": classification.notification_metadata if classification else None,
    }


class ImService:
    def __init__(
        self,
        mobile: MobileTaskService,
        *,
        observer: ImClassificationObserver | None = None,
        receive_only: bool = False,
        legacy_xianyu_device_ids: frozenset[str] = frozenset(),
    ) -> None:
        self.mobile = mobile
        self.database = mobile.database
        self.observer = observer
        self.receive_only = receive_only
        self.legacy_xianyu_device_ids = legacy_xianyu_device_ids
        if self.observer is not None:
            self.observer.persist = self._persist_assessment

    async def _persist_assessment(
        self,
        observation: InboundObservation,
        assessment: MessageAssessment,
    ) -> None:
        await persist_assessment(self.database, observation, assessment)

    async def _submit_observation(self, observation: InboundObservation) -> None:
        if self.observer is None:
            return
        try:
            state = self.observer.submit(observation)
        except Exception:
            state = "INTERNAL_ERROR"
        if state != "PENDING":
            await self.observer.record_result(observation, MessageAssessment(status=state))

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

    async def upsert_config(
        self, actor: Any, device_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        # Device-side monitoring configuration is a device write: the operator
        # inbox UI gates it on ``device.control`` and the API enforces the same
        # permission so read-only roles cannot change it with a raw credential.
        require_permissions(actor.roles, Permission.DEVICE_CONTROL)
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
                    device_id=device_id,
                    tenant_id=str(actor.tenant_id),
                    platforms=platforms,
                    mode=mode,
                    duty_start=duty_start,
                    duty_end=duty_end,
                    enabled=enabled,
                    updated_at=now,
                    updated_by=str(actor.user_id),
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

    def _config_view(self, row: ImMonitorConfigRow | None, device_id: str) -> dict[str, Any]:
        if row is None:
            return {
                "deviceId": device_id,
                "receiveOnly": self.receive_only,
                "enabled": True,
                "platforms": ["xianyu"],
                "mode": "NOTIFICATION",
                "dutyStart": "09:00",
                "dutyEnd": "23:00",
                "updatedAt": None,
            }
        return {
            "deviceId": row.device_id,
            "receiveOnly": self.receive_only,
            "enabled": row.enabled,
            "platforms": row.platforms,
            "mode": row.mode,
            "dutyStart": row.duty_start,
            "dutyEnd": row.duty_end,
            "updatedAt": row.updated_at,
        }

    async def ingest(self, binding_row: Any, items: list[dict[str, Any]]) -> dict[str, int]:
        if not 1 <= len(items) <= MAX_BATCH:
            raise ConflictError(f"batch must contain 1..{MAX_BATCH} messages")
        now = _now()
        accepted = 0
        duplicates = 0
        observations: list[InboundObservation] = []
        async with self.database.unit_of_work() as session:
            for item in items:
                platform = item["platform"]
                if platform != PLATFORM:
                    raise ConflictError("platform must be xianyu")
                peer_key = item["peerKey"].strip()
                peer_name = item["peerName"].strip()
                text = canonical_text(item["text"])
                if not peer_key or len(peer_key) > 128 or not peer_name or len(peer_name) > 128:
                    raise ConflictError("peer identity is invalid")
                if not text or not text.strip():
                    continue
                occurred = item["occurredAt"]
                if occurred.tzinfo is None:
                    occurred = occurred.replace(tzinfo=UTC)
                key = _dedupe_key(binding_row.device_id, platform, peer_key, occurred, text)
                # Recognize old server hashes without rewriting historical evidence.
                legacy_text = item["text"]
                if len(legacy_text) > MAX_TEXT:
                    legacy_text = TRUNCATED_PREFIX + legacy_text[:MAX_TEXT]
                legacy_keys = {
                    hashlib.sha256(
                        (
                            f"{binding_row.device_id}|{peer_key}|{int(occurred.timestamp())}|{body}"
                        ).encode()
                    ).hexdigest()
                    for body in (text, legacy_text)
                }
                existing = await session.scalar(
                    select(ImMessageRow)
                    .join(ImThreadRow, ImMessageRow.thread_id == ImThreadRow.id)
                    .where(
                        ImMessageRow.dedupe_key.in_({key, *legacy_keys}),
                        ImMessageRow.tenant_id == binding_row.tenant_id,
                        ImThreadRow.device_id == binding_row.device_id,
                        ImThreadRow.platform == platform,
                        ImThreadRow.peer_key == peer_key,
                    )
                    .limit(1)
                )
                if existing is not None:
                    duplicates += 1
                    continue
                thread = await session.scalar(
                    select(ImThreadRow)
                    .where(
                        ImThreadRow.tenant_id == binding_row.tenant_id,
                        ImThreadRow.device_id == binding_row.device_id,
                        ImThreadRow.platform == platform,
                        ImThreadRow.peer_key == peer_key,
                    )
                    .with_for_update()
                )
                if thread is None:
                    thread = ImThreadRow(
                        id=str(uuid.uuid4()),
                        tenant_id=binding_row.tenant_id,
                        device_id=binding_row.device_id,
                        platform=platform,
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
                message_id = str(uuid.uuid4())
                session.add(
                    ImMessageRow(
                        id=message_id,
                        tenant_id=binding_row.tenant_id,
                        thread_id=thread.id,
                        direction="IN",
                        content_type="TEXT",
                        text_content=text,
                        occurred_at=occurred,
                        dedupe_key=key,
                        # Inbound push is an observed fact on the device.
                        delivery_state="DELIVERED",
                        created_at=now,
                    )
                )
                await session.flush()
                classification = new_classification(
                    message_id,
                    binding_row.tenant_id,
                    peer_name,
                    text,
                    item.get("notificationMetadata"),
                )
                classification.model_status = "PENDING" if self.observer else "DISABLED"
                session.add(classification)
                thread.peer_name = peer_name
                latest_at = thread.last_message_at
                if latest_at.tzinfo is None:
                    latest_at = latest_at.replace(tzinfo=UTC)
                if occurred >= latest_at:
                    thread.last_message_at = occurred
                    thread.last_direction = "IN"
                thread.unread_count += 1
                thread.updated_at = now
                accepted += 1
                observations.append(
                    InboundObservation(
                        message_id=message_id,
                        device_id=binding_row.device_id,
                        platform=platform,
                        title=peer_name,
                        text=text,
                        notification_metadata=item.get("notificationMetadata"),
                    )
                )
        # Only committed, non-duplicate messages may leave the receiving service.
        if self.observer is not None:
            for observation in observations:
                await self._submit_observation(observation)
        return {"accepted": accepted, "duplicates": duplicates}

    async def list_threads(
        self,
        actor: Any,
        device_id: str | None,
        unread_only: bool,
        after: str | None,
        limit: int,
        bucket: str = "all",
    ) -> list[dict[str, Any]]:
        async with self.database.unit_of_work() as session:
            # Rank within the selected bucket first; unrelated newer notices must
            # not move or replace the summary of a user-message thread.
            ranked = (
                select(
                    ImMessageRow.id.label("message_id"),
                    ImMessageRow.thread_id,
                    ImMessageRow.occurred_at,
                    func.row_number()
                    .over(
                        partition_by=ImMessageRow.thread_id,
                        order_by=(
                            ImMessageRow.occurred_at.desc(),
                            ImMessageRow.created_at.desc(),
                            ImMessageRow.id.desc(),
                        ),
                    )
                    .label("rank"),
                )
                .outerjoin(ImClassificationRow, ImClassificationRow.message_id == ImMessageRow.id)
                .where(ImMessageRow.tenant_id == str(actor.tenant_id), bucket_predicate(bucket))
                .subquery()
            )
            query = (
                select(ImThreadRow, ImMessageRow, ImClassificationRow)
                .join(ranked, and_(ranked.c.thread_id == ImThreadRow.id, ranked.c.rank == 1))
                .join(ImMessageRow, ImMessageRow.id == ranked.c.message_id)
                .outerjoin(ImClassificationRow, ImClassificationRow.message_id == ImMessageRow.id)
                .where(ImThreadRow.tenant_id == str(actor.tenant_id))
            )
            if device_id:
                query = query.where(ImThreadRow.device_id == device_id)
            if unread_only:
                query = query.where(ImThreadRow.unread_count > 0)
            if after:
                anchor = (await session.execute(query.where(ImThreadRow.id == after))).first()
                if anchor is None:
                    raise NotFoundError("thread was not found")
                query = query.where(
                    or_(
                        ranked.c.occurred_at < anchor[1].occurred_at,
                        and_(
                            ranked.c.occurred_at == anchor[1].occurred_at,
                            ImThreadRow.id < anchor[0].id,
                        ),
                    )
                )
            rows = (
                await session.execute(
                    query.order_by(ranked.c.occurred_at.desc(), ImThreadRow.id.desc()).limit(limit)
                )
            ).all()
            views: list[dict[str, Any]] = []
            for row, last_message, classification in rows:
                view = _thread_view(row, last_message.text_content)
                view["lastMessageAt"] = _message_view(last_message)["occurredAt"]
                view["lastDirection"] = last_message.direction
                view["lastMessageClassification"] = (
                    classification_view(classification) if last_message.direction == "IN" else None
                )
                views.append(view)
            return views

    async def bucket_counts(
        self,
        actor: Any,
        device_id: str | None,
        unread_only: bool,
    ) -> dict[str, int]:
        async with self.database.unit_of_work() as session:
            query = (
                select(func.count(func.distinct(ImThreadRow.id)))
                .select_from(ImThreadRow)
                .join(ImMessageRow, ImMessageRow.thread_id == ImThreadRow.id)
                .outerjoin(ImClassificationRow, ImClassificationRow.message_id == ImMessageRow.id)
                .where(
                    ImThreadRow.tenant_id == str(actor.tenant_id),
                    ImMessageRow.tenant_id == str(actor.tenant_id),
                )
            )
            if device_id:
                query = query.where(ImThreadRow.device_id == device_id)
            if unread_only:
                query = query.where(ImThreadRow.unread_count > 0)
            return {
                bucket: int(await session.scalar(query.where(bucket_predicate(bucket))) or 0)
                for bucket in ("all", "user", "notice", "review")
            }

    async def _owned_thread(self, session: Any, actor: Any, thread_id: str) -> ImThreadRow:
        row = await session.get(ImThreadRow, thread_id, with_for_update=True)
        if row is None or row.tenant_id != str(actor.tenant_id):
            raise NotFoundError("thread was not found")
        assert isinstance(row, ImThreadRow)
        return row

    async def list_messages(
        self,
        actor: Any,
        thread_id: str,
        after: str | None,
        limit: int,
        latest: bool = False,
        bucket: str = "all",
    ) -> list[dict[str, Any]]:
        async with self.database.unit_of_work() as session:
            thread = await self._owned_thread(session, actor, thread_id)
            predicate = bucket_predicate(bucket)
            if bucket == "user":
                predicate = or_(predicate, ImMessageRow.direction == "OUT")
            query = (
                select(ImMessageRow, ImClassificationRow)
                .outerjoin(ImClassificationRow, ImClassificationRow.message_id == ImMessageRow.id)
                .where(
                    ImMessageRow.thread_id == thread.id,
                    ImMessageRow.tenant_id == str(actor.tenant_id),
                    predicate,
                )
            )
            if after:
                anchor = await session.get(ImMessageRow, after)
                if anchor is None or anchor.thread_id != thread.id:
                    raise NotFoundError("message was not found")
                query = query.where(
                    or_(
                        ImMessageRow.occurred_at > anchor.occurred_at,
                        and_(
                            ImMessageRow.occurred_at == anchor.occurred_at,
                            ImMessageRow.id > anchor.id,
                        ),
                    )
                )
            newest = latest and not after
            ordering = (
                (ImMessageRow.occurred_at.desc(), ImMessageRow.id.desc())
                if newest
                else (ImMessageRow.occurred_at.asc(), ImMessageRow.id.asc())
            )
            rows = list((await session.execute(query.order_by(*ordering).limit(limit))).all())
            if newest:
                rows.reverse()
            return [_message_view(row, classification) for row, classification in rows]

    async def _classification_target(
        self,
        session: Any,
        actor: Any,
        message_id: str,
        expected_version: int,
    ) -> tuple[ImMessageRow, ImClassificationRow]:
        message = await session.scalar(
            select(ImMessageRow)
            .where(ImMessageRow.id == message_id, ImMessageRow.tenant_id == str(actor.tenant_id))
            .with_for_update()
        )
        if message is None:
            raise NotFoundError("message was not found")
        if message.direction != "IN":
            raise ConflictError("ONLY_INBOUND_CLASSIFICATION")
        row = await session.get(ImClassificationRow, message_id)
        if expected_version != (row.version if row else 0):
            raise ConflictError("CLASSIFICATION_VERSION_CONFLICT")
        if row is None:
            row = new_classification(message.id, message.tenant_id, "", "")
            # Creating a manual sidecar must not silently classify old history.
            row.machine_status = "UNCLASSIFIED"
            session.add(row)
        else:
            row.version += 1
        row.updated_at = _now()
        return message, row

    async def correct_classification(
        self,
        actor: Any,
        message_id: str,
        expected_version: int,
        category: str | None,
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_CONTROL)
        async with self.database.unit_of_work() as session:
            message, row = await self._classification_target(
                session, actor, message_id, expected_version
            )
            previous = row.manual_category
            row.manual_category = category
            row.reviewed_at = _now()
            row.reviewed_by = str(actor.user_id)
            session.add(
                AuditEventRow(
                    id=str(uuid.uuid4()),
                    tenant_id=str(actor.tenant_id),
                    actor_type="user",
                    actor_id=str(actor.user_id),
                    action="im.message.classify",
                    resource_type="im_message",
                    resource_id=message_id,
                    request_id=actor.request_id,
                    result="SUCCESS",
                    metadata_json={
                        "previousManualCategory": previous,
                        "manualCategory": category,
                        "expectedVersion": expected_version,
                        "version": row.version,
                    },
                    occurred_at=_now(),
                )
            )
            return _message_view(message, row)

    async def reclassify(
        self,
        actor: Any,
        message_id: str,
        expected_version: int,
    ) -> dict[str, Any]:
        require_permissions(actor.roles, Permission.DEVICE_CONTROL)
        async with self.database.unit_of_work() as session:
            message, row = await self._classification_target(
                session, actor, message_id, expected_version
            )
            thread = await session.get(ImThreadRow, message.thread_id)
            assert thread is not None
            title = row.notification_title or thread.peer_name
            category, rule = notification_rule(
                title, message.text_content, row.notification_metadata
            )
            row.machine_category = category
            row.machine_source = "RULE" if rule else "UNCLASSIFIED"
            row.machine_status = "RULE_CLASSIFIED" if rule else "NEEDS_REVIEW"
            row.rule_code = rule
            row.generation += 1
            row.model_status = "PENDING" if self.observer else "DISABLED"
            observation = InboundObservation(
                message.id,
                thread.device_id,
                thread.platform,
                title,
                message.text_content,
                row.notification_metadata,
                row.generation,
            )
            session.add(
                AuditEventRow(
                    id=str(uuid.uuid4()),
                    tenant_id=str(actor.tenant_id),
                    actor_type="user",
                    actor_id=str(actor.user_id),
                    action="im.message.reclassify",
                    resource_type="im_message",
                    resource_id=message_id,
                    request_id=actor.request_id,
                    result="SUCCESS",
                    metadata_json={
                        "expectedVersion": expected_version,
                        "version": row.version,
                        "generation": row.generation,
                    },
                    occurred_at=_now(),
                )
            )
        await self._submit_observation(observation)
        async with self.database.unit_of_work() as session:
            updated = await session.get(ImClassificationRow, message_id)
            return _message_view(message, updated)

    async def mark_read(self, actor: Any, thread_id: str) -> dict[str, Any]:
        async with self.database.unit_of_work() as session:
            thread = await self._owned_thread(session, actor, thread_id)
            thread.unread_count = 0
            thread.updated_at = _now()
            return _thread_view(thread)

    async def reply(self, actor: Any, thread_id: str, text: str) -> dict[str, Any]:
        # A reply sends a real outbound message through the device: require the
        # same ``device.control`` write permission the operator inbox UI uses.
        require_permissions(actor.roles, Permission.DEVICE_CONTROL)
        if self.receive_only:
            raise ConflictError("IM_RECEIVE_ONLY")
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

            reply_ordinal = (
                await session.scalar(
                    select(sa_func.count())
                    .select_from(ImMessageRow)
                    .where(
                        ImMessageRow.thread_id == thread.id,
                        ImMessageRow.direction == "OUT",
                    )
                )
                or 0
            )
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
                    # Dispatched, not yet delivered: settled when the task ends.
                    delivery_state="PENDING",
                    created_at=now,
                )
            )
            thread.last_message_at = now
            thread.last_direction = "OUT"
            thread.updated_at = now
            return {"taskId": task_view["id"], "threadId": thread.id}


def _reply_steps(peer_name: str, text: str) -> list[dict[str, Any]]:
    return [
        {
            "stepId": "find-messages-tab",
            "locatorRef": "xianyu_messages_tab",
            "timeoutMs": 8000,
            "action": "ui.find",
        },
        {
            "stepId": "open-messages-tab",
            "locatorRef": "xianyu_messages_tab",
            "timeoutMs": 8000,
            "action": "ui.tap",
        },
        {
            "stepId": "open-conversation",
            "timeoutMs": 8000,
            "action": "ui.tapText",
            "value": peer_name[:64],
        },
        {
            "stepId": "wait-chat-input",
            "locatorRef": "xianyu_chat_input",
            "timeoutMs": 8000,
            "action": "ui.wait",
            "condition": "EXISTS",
            "pollMs": 200,
        },
        {
            "stepId": "fill-reply",
            "locatorRef": "xianyu_chat_input",
            "timeoutMs": 20000,
            "action": "ui.input",
            "value": text,
            "replace": True,
            "sensitive": False,
        },
        {
            "stepId": "send-reply",
            "locatorRef": "xianyu_chat_send",
            "timeoutMs": 8000,
            "action": "ui.tap",
        },
    ]
