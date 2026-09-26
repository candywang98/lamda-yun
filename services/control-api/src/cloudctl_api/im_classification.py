"""Notification-purpose rules and versioned sidecars, independent of message truth."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, select

from .db import ImClassificationRow, ImMessageRow
from .im_classifier import MessageAssessment
from .im_observer import InboundObservation


def notification_rule(
    title: str,
    text: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[str, str | None]:
    """Only narrow, combined signals qualify; arbitrary buyer text stays reviewable."""
    official = title.strip() in {
        "闲鱼",
        "闲鱼官方",
        "闲鱼小助手",
        "闲鱼通知",
        "系统通知",
        "交易通知",
        "服务通知",
    }
    marketing = re.search(r"为你推荐|猜你喜欢|限时优惠|领取优惠券|活动开始|精选好物", text)
    system = re.search(r"订单|交易|账号|账户|物流|发货|退款|支付|安全|违规", text)
    if official and marketing:
        return "PROMOTION", "OFFICIAL_PROMOTION"
    if official and system:
        return "SYSTEM_NOTICE", "OFFICIAL_TRANSACTION_NOTICE"
    # Do not mistake an official-source generic push for a named-peer conversation.
    if official:
        return "UNKNOWN", None
    summary = re.fullmatch(r"(?:给你)?发来(?:了)?(?:一条)?新消息[。！!]?", text.strip())
    if title.strip() and summary:
        return "HUMAN_MESSAGE", "NAMED_PEER_MESSAGE_SUMMARY"
    return "UNKNOWN", None


def new_classification(
    message_id: str,
    tenant_id: str,
    title: str,
    text: str,
    metadata: dict[str, Any] | None = None,
) -> ImClassificationRow:
    category, rule = notification_rule(title, text, metadata)
    return ImClassificationRow(
        message_id=message_id,
        tenant_id=tenant_id,
        notification_metadata=metadata,
        notification_title=title or None,
        machine_category=category,
        machine_source="RULE" if rule else "UNCLASSIFIED",
        machine_status="RULE_CLASSIFIED" if rule else "NEEDS_REVIEW",
        rule_code=rule,
        version=1,
        generation=1,
        updated_at=datetime.now(UTC),
    )


def classification_view(row: ImClassificationRow | None) -> dict[str, Any]:
    if row is None:
        return {
            "category": "UNKNOWN",
            "predictedCategory": None,
            "confidence": None,
            "source": "UNCLASSIFIED",
            "status": "UNCLASSIFIED",
            "modelStatus": None,
            "ruleCode": None,
            "reviewedAt": None,
            "reviewedBy": None,
            "version": 0,
        }
    manual = row.manual_category is not None
    return {
        "category": row.manual_category if manual else row.machine_category,
        "predictedCategory": row.predicted_category,
        "confidence": row.confidence,
        "source": "MANUAL" if manual else row.machine_source,
        "status": "MANUAL" if manual else row.machine_status,
        "modelStatus": row.model_status,
        "ruleCode": row.rule_code,
        "reviewedAt": row.reviewed_at,
        "reviewedBy": row.reviewed_by,
        "version": row.version,
    }


def bucket_predicate(bucket: str) -> Any:
    category = func.coalesce(
        ImClassificationRow.manual_category, ImClassificationRow.machine_category, "UNKNOWN"
    )
    if bucket == "all":
        return True
    values = {
        "user": ["HUMAN_MESSAGE"],
        "notice": ["SYSTEM_NOTICE", "PROMOTION"],
        "review": ["UNKNOWN"],
    }
    return and_(ImMessageRow.direction == "IN", category.in_(values[bucket]))


async def persist_assessment(
    database: Any,
    observation: InboundObservation,
    assessment: MessageAssessment,
) -> None:
    async with database.unit_of_work() as session:
        # All correction/model writers lock the same original row, including when
        # no sidecar exists yet. Model generations reject obsolete retry results.
        message = await session.scalar(
            select(ImMessageRow).where(ImMessageRow.id == observation.message_id).with_for_update()
        )
        if message is None:
            return
        row = await session.get(ImClassificationRow, message.id)
        if row is None or row.generation != observation.generation:
            return
        row.model_status = assessment.status
        if assessment.predicted_category is not None:
            row.predicted_category = assessment.predicted_category
            row.confidence = assessment.confidence
        if row.rule_code is None:
            row.machine_category = assessment.category
            row.machine_source = (
                "MODEL" if assessment.predicted_category is not None else "UNCLASSIFIED"
            )
            row.machine_status = (
                "MODEL_CLASSIFIED" if assessment.status == "CLASSIFIED" else "NEEDS_REVIEW"
            )
        row.version += 1
        row.updated_at = datetime.now(UTC)
