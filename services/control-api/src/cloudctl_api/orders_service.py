"""Order sync slice 1: companion push and operator query (order-sync/20260915.1).

Companion collects read-only order rows from the xianyu sold/bought list and
pushes them in bounded batches; the server resolves each row against the
natural key (tenant, device, platform, order_key) and keeps the first snapshot
it saw (slice 1 never rewrites). Rows without a usable order_key are rejected
upstream at the DTO layer: 宁缺勿假键.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from cloudctl_domain import NotFoundError, ValidationError
from sqlalchemy import func, select

from .db import Database, OrderRow
from .mobile_service import _now

PLATFORM = "xianyu"
MAX_BATCH = 20
ORDER_KEY_MAX = 128
ITEM_TITLE_MAX = 256
BUYER_NAME_MAX = 128
STATUS_TEXT_MAX = 64


def parse_occurred_at(value: str | None) -> datetime | None:
    """Best-effort ISO parse of the page time; failures become NULL.

    Contract §2: occurred_at 可空，页面时间解析失败则空. The row is an observed
    fact and must not be dropped because its timestamp text was unreadable.
    """

    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _order_view(row: OrderRow, *, include_raw: bool) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": row.id,
        "deviceId": row.device_id,
        "platform": row.platform,
        "direction": row.direction,
        "orderKey": row.order_key,
        "itemTitle": row.item_title,
        "buyerName": row.buyer_name,
        "amountCents": row.amount_cents,
        "statusText": row.status_text,
        "occurredAt": row.occurred_at,
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
    }
    if include_raw:
        view["raw"] = row.raw
    return view


class OrderService:
    """Ingest and query the collected order snapshots (tenant isolated)."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def ingest(self, binding_row: Any, orders: list[Any]) -> dict[str, int]:
        """Insert unseen order rows; existing natural keys are skipped.

        Returns {"accepted": n, "duplicates": m}; duplicate means the exact
        natural key was already stored (replay-safe, snapshot not updated).
        """

        if not 1 <= len(orders) <= MAX_BATCH:
            raise ValidationError(f"orders batch must contain 1..{MAX_BATCH} items")
        now = _now()
        accepted = 0
        duplicates = 0
        async with self.database.unit_of_work() as session:
            for item in orders:
                order_key = item.order_key.strip()[:ORDER_KEY_MAX]
                occurred = parse_occurred_at(item.occurred_at)
                existing = await session.scalar(
                    select(OrderRow).where(
                        OrderRow.tenant_id == binding_row.tenant_id,
                        OrderRow.device_id == binding_row.device_id,
                        OrderRow.platform == PLATFORM,
                        OrderRow.order_key == order_key,
                    )
                )
                if existing is not None:
                    duplicates += 1
                    continue
                session.add(
                    OrderRow(
                        id=str(uuid.uuid4()),
                        tenant_id=binding_row.tenant_id,
                        device_id=binding_row.device_id,
                        platform=PLATFORM,
                        direction=item.direction,
                        order_key=order_key,
                        item_title=_truncate(item.item_title, ITEM_TITLE_MAX),
                        buyer_name=_truncate(item.buyer_name, BUYER_NAME_MAX),
                        amount_cents=item.amount_cents,
                        status_text=_truncate(item.status_text, STATUS_TEXT_MAX),
                        occurred_at=occurred,
                        raw=item.raw,
                        created_at=now,
                        updated_at=now,
                    )
                )
                accepted += 1
        return {"accepted": accepted, "duplicates": duplicates}

    async def list_orders(
        self,
        actor: Any,
        device_id: str | None,
        direction: str | None,
        status_text: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        async with self.database.unit_of_work() as session:
            filters = [OrderRow.tenant_id == str(actor.tenant_id)]
            if device_id:
                filters.append(OrderRow.device_id == device_id)
            if direction:
                filters.append(OrderRow.direction == direction)
            if status_text:
                filters.append(OrderRow.status_text == status_text)
            total = (
                await session.scalar(select(func.count()).select_from(OrderRow).where(*filters))
            ) or 0
            rows = (
                await session.scalars(
                    select(OrderRow)
                    .where(*filters)
                    # occurred_at DESC with NULLs last on both SQLite and
                    # PostgreSQL; created_at breaks ties deterministically.
                    .order_by(OrderRow.occurred_at.desc(), OrderRow.created_at.desc(), OrderRow.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return {
                "items": [_order_view(row, include_raw=False) for row in rows],
                "total": int(total),
            }

    async def get_order(self, actor: Any, order_id: str) -> dict[str, Any]:
        async with self.database.unit_of_work() as session:
            row = await session.get(OrderRow, order_id)
            if row is None or row.tenant_id != str(actor.tenant_id):
                raise NotFoundError("order was not found")
            return _order_view(row, include_raw=True)


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    return text[:limit]
