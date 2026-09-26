"""Fleet order pagination / dedupe-upsert / checkpoint / history (O10).

Sits ABOVE the accepted order-sync modules without touching them:
- ``orders_service.OrderService`` (slice 1) keeps its frozen first-write-wins
  batch endpoint ``/companion/v2/orders/batch``;
- ``xianyu_orders.XianyuOrdersService`` (slice 1/2) keeps the read-only
  collect-run orchestration (ui.readOrders / ui.swipeUp steps).

This module adds the O10 fleet layer on top of the same ``xianyu_order``
table plus two new bookkeeping tables (migration 20260917_0026; the ORM
rows live here because ``db.py`` is outside this slice's write set):

- ``fleet_order_page``       — one row per collected screen (page summary):
  run/account attribution, ordinal, new/overlap counts, empty/partial flags.
  ``(tenant, device, run_key, screen)`` unique: an offline replay of the
  same screen stores exactly one page (no double counting).
- ``fleet_order_checkpoint`` — ONE active checkpoint per
  ``(tenant, device, platform, direction)`` binding account + schema
  version + current run: resume is refused for a different account
  (设备 A 的订单断点不归 B 账号), a different schema version, or a silent
  screen skip; replays of already-seen screens stay idempotent.

Dedupe upgrade (O10 §1): rows are keyed by the real visible order id when
the pushed ``order_key`` is one (15..24 digit run); every other key is
stored with an explicit ``raw["dedupeMarker"] = "MISSING_ID"`` — the
composite slice1 key stays a degraded marker, never a fabricated platform
id. Status changes (and null-field fills) now UPSERT the snapshot instead
of being silently dropped.

History (O10 §3): ``GET /api/v1/fleet/orders/history`` is cursor-paginated,
tenant-scoped on every page, annotates each run's collection window
(start/end timestamps), missing screens (ordinal gaps), empty/partial
screens and the real/degraded dedupe-marker split. Queries for another
tenant return empty (list) — never a leak.

Read-only invariant (O10 §4): this module contains no step builders, no
ledger-gated clicks, no task orchestration — pushes only record observed
rows; nothing here can imply 发货/评价/交易 actions.
"""

from __future__ import annotations

import base64
import json
import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, cast

from cloudctl_domain import ConflictError, NotFoundError, ValidationError
from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .auth import current_actor
from .db import Base, Database, DeviceRow, OrderRow, TimestampMixin
from .mobile_routes import binding
from .mobile_service import _now
from .orders_routes import OrderIn
from .orders_service import (
    BUYER_NAME_MAX,
    ITEM_TITLE_MAX,
    MAX_BATCH,
    ORDER_KEY_MAX,
    PLATFORM,
    STATUS_TEXT_MAX,
    _truncate,
    parse_occurred_at,
)

# ---------------------------------------------------------------------------
# ORM rows (shared Base metadata; SQL migration 20260917_0026)
# ---------------------------------------------------------------------------


class FleetOrderPageRow(Base, TimestampMixin):
    """One collected screen per (tenant, device, run, screen) — page summary."""

    __tablename__ = "fleet_order_page"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("device.id"), index=True, nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), default="xianyu", nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    account_key: Mapped[str] = mapped_column(String(128), nullable=False)
    run_key: Mapped[str] = mapped_column(String(128), nullable=False)
    screen: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_seen: Mapped[int] = mapped_column(Integer, nullable=False)
    new_keys: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_keys: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overlap: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    partial_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    empty_page: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "device_id",
            "run_key",
            "screen",
            name="uq_fleet_order_page_screen",
        ),
        CheckConstraint("platform IN ('xianyu')", name="ck_fleet_order_page_platform"),
        CheckConstraint("direction IN ('SOLD', 'BOUGHT')", name="ck_fleet_order_page_direction"),
        CheckConstraint("screen >= 1", name="ck_fleet_order_page_screen_positive"),
        CheckConstraint(
            "rows_seen >= 0 AND new_keys >= 0 AND overlap >= 0", name="ck_fleet_order_page_counts"
        ),
    )


class FleetOrderCheckpointRow(Base, TimestampMixin):
    """ONE active resume point per (tenant, device, platform, direction)."""

    __tablename__ = "fleet_order_checkpoint"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("device.id"), index=True, nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), default="xianyu", nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    account_key: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    run_key: Mapped[str] = mapped_column(String(128), nullable=False)
    last_screen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    seen_keys: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "device_id",
            "platform",
            "direction",
            name="uq_fleet_order_checkpoint_binding",
        ),
        CheckConstraint("platform IN ('xianyu')", name="ck_fleet_order_checkpoint_platform"),
        CheckConstraint(
            "direction IN ('SOLD', 'BOUGHT')", name="ck_fleet_order_checkpoint_direction"
        ),
        CheckConstraint("schema_version >= 1", name="ck_fleet_order_checkpoint_version"),
        CheckConstraint(
            "last_screen >= 0 AND seen_keys >= 0", name="ck_fleet_order_checkpoint_counts"
        ),
    )


# ---------------------------------------------------------------------------
# Dedupe markers (O10 §1)
# ---------------------------------------------------------------------------

#: A pushed order_key that is a plain 15..24 digit run is a REAL platform
#: order id; anything else (the slice1 composite key) is a degraded key.
REAL_ORDER_ID = re.compile(r"^[0-9]{15,24}$")

MARKER_REAL_ID = "REAL_ID"
MARKER_MISSING_ID = "MISSING_ID"


def dedupe_marker(order_key: str) -> str:
    return MARKER_REAL_ID if REAL_ORDER_ID.match(order_key) else MARKER_MISSING_ID


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class FleetOrderScreenIn(BaseModel):
    """One collected screen pushed per read (O10 §2 page summary + rows)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    run_key: str = Field(alias="runKey", min_length=1, max_length=128)
    account_key: str = Field(alias="accountKey", min_length=1, max_length=128)
    schema_version: int = Field(alias="schemaVersion", ge=1, le=99)
    screen: int = Field(ge=1, le=50)
    direction: Literal["SOLD", "BOUGHT"]
    rows: list[OrderIn] = Field(default_factory=list, max_length=MAX_BATCH)
    partial_rows: list[int] = Field(alias="partialRows", default_factory=list, max_length=50)
    collected_at: str | None = Field(alias="collectedAt", default=None, max_length=64)


def _checkpoint_view(row: FleetOrderCheckpointRow) -> dict[str, Any]:
    return {
        "deviceId": row.device_id,
        "direction": row.direction,
        "accountKey": row.account_key,
        "schemaVersion": row.schema_version,
        "runKey": row.run_key,
        "lastScreen": row.last_screen,
        "seenKeys": row.seen_keys,
        "updatedAt": row.updated_at,
    }


def _history_item_view(row: OrderRow) -> dict[str, Any]:
    raw = row.raw if isinstance(row.raw, dict) else None
    return {
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
        "dedupeMarker": (raw or {}).get("dedupeMarker"),
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
    }


def _window_view(rows: list[FleetOrderPageRow]) -> dict[str, Any]:
    screens = sorted({row.screen for row in rows})
    present = set(screens)
    timestamps = [row.collected_at for row in rows if row.collected_at is not None]
    return {
        "runKey": rows[0].run_key,
        "accountKey": rows[0].account_key,
        "deviceId": rows[0].device_id,
        "direction": rows[0].direction,
        "startedAt": min(timestamps) if timestamps else None,
        "endedAt": max(timestamps) if timestamps else None,
        "screensPresent": screens,
        "missingScreens": [
            n for n in range(1, (screens[-1] if screens else 0) + 1) if n not in present
        ],
        "emptyScreens": sorted({row.screen for row in rows if row.empty_page}),
        "partialScreens": sorted({row.screen for row in rows if row.partial_rows > 0}),
        "newKeys": sum(row.new_keys for row in rows),
        "updatedKeys": sum(row.updated_keys for row in rows),
        "overlap": sum(row.overlap for row in rows),
    }


def _encode_cursor(offset: int) -> str:
    payload = json.dumps({"v": 1, "o": offset}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _decode_cursor(raw: str | None) -> int:
    if raw is None or raw == "":
        return 0
    try:
        padded = raw + "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except (ValueError, json.JSONDecodeError):
        raise ValidationError("cursor is malformed") from None
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise ValidationError("cursor is malformed")
    offset = payload.get("o")
    if not isinstance(offset, int) or isinstance(offset, bool) or not 0 <= offset <= 100_000:
        raise ValidationError("cursor offset is out of range")
    return offset


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class FleetOrdersService:
    """Page push (dedupe-upsert + checkpoint) and cursor history query."""

    def __init__(self, database: Database) -> None:
        self.database = database

    # -- companion push -----------------------------------------------------

    async def push_screen(self, binding_row: Any, body: FleetOrderScreenIn) -> dict[str, Any]:
        tenant_id = binding_row.tenant_id
        device_id = binding_row.device_id
        now = _now()
        collected_at = parse_occurred_at(body.collected_at)
        async with self.database.unit_of_work() as session:
            device = await session.get(DeviceRow, device_id)
            if device is None or device.tenant_id != tenant_id:
                raise NotFoundError("device was not found")

            checkpoint = await self._load_checkpoint(session, tenant_id, device_id, body.direction)
            replayed_page = False
            if checkpoint is None:
                checkpoint = FleetOrderCheckpointRow(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    device_id=device_id,
                    platform=PLATFORM,
                    direction=body.direction,
                    account_key=body.account_key,
                    schema_version=body.schema_version,
                    run_key=body.run_key,
                    last_screen=0,
                    seen_keys=0,
                    created_at=now,
                    updated_at=now,
                )
                session.add(checkpoint)
                await session.flush()
            else:
                self._guard_checkpoint(checkpoint, body)

            # Page row: (tenant, device, run_key, screen) unique — an offline
            # replay stores exactly one page per screen.
            page = await session.scalar(
                select(FleetOrderPageRow).where(
                    FleetOrderPageRow.tenant_id == tenant_id,
                    FleetOrderPageRow.device_id == device_id,
                    FleetOrderPageRow.run_key == body.run_key,
                    FleetOrderPageRow.screen == body.screen,
                )
            )
            if page is None:
                accepted, updated, duplicates = await self._upsert_orders(
                    session, tenant_id, device_id, body.rows, now
                )
                session.add(
                    FleetOrderPageRow(
                        id=str(uuid.uuid4()),
                        tenant_id=tenant_id,
                        device_id=device_id,
                        platform=PLATFORM,
                        direction=body.direction,
                        account_key=body.account_key,
                        run_key=body.run_key,
                        screen=body.screen,
                        rows_seen=len(body.rows),
                        new_keys=accepted,
                        updated_keys=updated,
                        overlap=duplicates,
                        partial_rows=len(body.partial_rows),
                        empty_page=len(body.rows) == 0,
                        collected_at=collected_at,
                        created_at=now,
                    )
                )
                if body.screen > checkpoint.last_screen:
                    checkpoint.last_screen = body.screen
                    checkpoint.seen_keys += accepted
                checkpoint.run_key = body.run_key
                checkpoint.account_key = body.account_key
                checkpoint.updated_at = now
                await session.flush()
            else:
                # 断网重传：同屏重放不重复计数、不回退断点、不改账号归属。
                replayed_page = True
                accepted, updated, duplicates = 0, 0, len(body.rows)

            return {
                "accepted": accepted,
                "updated": updated,
                "duplicates": duplicates,
                "screen": body.screen,
                "replayed": replayed_page,
                "checkpoint": _checkpoint_view(checkpoint),
            }

    def _guard_checkpoint(
        self, checkpoint: FleetOrderCheckpointRow, body: FleetOrderScreenIn
    ) -> None:
        """O10 §2 断点绑定：版本 → 账号 → run → 屏序守卫（拒绝即 409）。"""
        if checkpoint.schema_version != body.schema_version:
            raise ConflictError(
                "order checkpoint schema version mismatch: restart the run from screen 1"
            )
        if checkpoint.run_key == body.run_key and checkpoint.account_key != body.account_key:
            # A 设备订单不归 B 账号：别人的 run 不许换账号续推。
            raise ConflictError(
                "order run belongs to another account; orders stay attributed to it"
            )
        if body.run_key != checkpoint.run_key:
            if body.screen != 1:
                raise ConflictError(
                    "order checkpoint is bound to another run; restart from screen 1"
                )
            return  # 新 run 从第 1 屏开始：允许，并把断点重绑到新 run/账号。
        if body.screen > checkpoint.last_screen + 1:
            # 缺失页不允许被默默跳过（历史报表会如实标注缺页，但推送侧先拒绝）。
            raise ConflictError(
                f"order screen gap: checkpoint is at screen {checkpoint.last_screen}, "
                f"refusing screen {body.screen}"
            )

    async def _load_checkpoint(
        self, session: AsyncSession, tenant_id: str, device_id: str, direction: str
    ) -> FleetOrderCheckpointRow | None:
        return cast(
            FleetOrderCheckpointRow | None,
            await session.scalar(
                select(FleetOrderCheckpointRow).where(
                    FleetOrderCheckpointRow.tenant_id == tenant_id,
                    FleetOrderCheckpointRow.device_id == device_id,
                    FleetOrderCheckpointRow.platform == PLATFORM,
                    FleetOrderCheckpointRow.direction == direction,
                )
            ),
        )

    async def _upsert_orders(
        self, session: Any, tenant_id: str, device_id: str, rows: list[Any], now: Any
    ) -> tuple[int, int, int]:
        """O10 §1 去重升级：新键插入（带降级标记），状态变化/补空 upsert，纯重复跳过。"""
        accepted = updated = duplicates = 0
        for item in rows:
            order_key = item.order_key.strip()[:ORDER_KEY_MAX]
            marker = dedupe_marker(order_key)
            existing = await session.scalar(
                select(OrderRow).where(
                    OrderRow.tenant_id == tenant_id,
                    OrderRow.device_id == device_id,
                    OrderRow.platform == PLATFORM,
                    OrderRow.order_key == order_key,
                )
            )
            if existing is None:
                raw = dict(item.raw) if isinstance(item.raw, dict) else {}
                raw["dedupeMarker"] = marker
                session.add(
                    OrderRow(
                        id=str(uuid.uuid4()),
                        tenant_id=tenant_id,
                        device_id=device_id,
                        platform=PLATFORM,
                        direction=item.direction,
                        order_key=order_key,
                        item_title=_truncate(item.item_title, ITEM_TITLE_MAX),
                        buyer_name=_truncate(item.buyer_name, BUYER_NAME_MAX),
                        amount_cents=item.amount_cents,
                        status_text=_truncate(item.status_text, STATUS_TEXT_MAX),
                        occurred_at=parse_occurred_at(item.occurred_at),
                        raw=raw,
                        created_at=now,
                        updated_at=now,
                    )
                )
                accepted += 1
                continue
            incoming_status = _truncate(item.status_text, STATUS_TEXT_MAX)
            incoming_title = _truncate(item.item_title, ITEM_TITLE_MAX)
            incoming_buyer = _truncate(item.buyer_name, BUYER_NAME_MAX)
            incoming_occurred = parse_occurred_at(item.occurred_at)
            fills = (
                (existing.item_title is None and incoming_title is not None)
                or (existing.buyer_name is None and incoming_buyer is not None)
                or (existing.amount_cents is None and item.amount_cents is not None)
                or (existing.occurred_at is None and incoming_occurred is not None)
            )
            status_changed = incoming_status is not None and existing.status_text != incoming_status
            if status_changed or fills:
                if status_changed:
                    existing.status_text = incoming_status
                existing.item_title = existing.item_title or incoming_title
                existing.buyer_name = existing.buyer_name or incoming_buyer
                if existing.amount_cents is None:
                    existing.amount_cents = item.amount_cents
                if existing.occurred_at is None:
                    existing.occurred_at = incoming_occurred
                raw = dict(existing.raw) if isinstance(existing.raw, dict) else {}
                raw.setdefault("dedupeMarker", marker)
                existing.raw = raw
                existing.updated_at = now
                updated += 1
            else:
                duplicates += 1
        return accepted, updated, duplicates

    # -- companion checkpoint ----------------------------------------------

    async def get_checkpoint(self, binding_row: Any, direction: str) -> dict[str, Any]:
        async with self.database.unit_of_work() as session:
            checkpoint = await self._load_checkpoint(
                session, binding_row.tenant_id, binding_row.device_id, direction
            )
            if checkpoint is None:
                raise NotFoundError("order checkpoint was not found")
            return _checkpoint_view(checkpoint)

    # -- operator history ---------------------------------------------------

    async def history(
        self,
        actor: Any,
        *,
        device_id: str | None,
        direction: str | None,
        status_text: str | None,
        account_key: str | None,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        """O10 §3 历史查询：游标分页 + 租户过滤 + 采集窗口/缺失页标注。

        跨租户语义与 slice1 一致：列表查询对他人租户返回空集，绝不泄漏。
        """
        tenant_id = str(actor.tenant_id)
        offset = _decode_cursor(cursor)
        async with self.database.unit_of_work() as session:
            filters = [OrderRow.tenant_id == tenant_id]
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
                    # Same deterministic ordering as slice1 (occurred_at DESC
                    # NULLs last, created_at DESC tiebreak, id final).
                    .order_by(OrderRow.occurred_at.desc(), OrderRow.created_at.desc(), OrderRow.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            items = [_history_item_view(row) for row in rows]

            window_filters = [
                FleetOrderPageRow.tenant_id == tenant_id,
                FleetOrderPageRow.platform == PLATFORM,
            ]
            if device_id:
                window_filters.append(FleetOrderPageRow.device_id == device_id)
            if direction:
                window_filters.append(FleetOrderPageRow.direction == direction)
            if account_key:
                window_filters.append(FleetOrderPageRow.account_key == account_key)
            page_rows = (
                await session.scalars(
                    select(FleetOrderPageRow)
                    .where(*window_filters)
                    .order_by(FleetOrderPageRow.created_at, FleetOrderPageRow.id)
                )
            ).all()

        by_run: dict[str, list[FleetOrderPageRow]] = {}
        for row in page_rows:
            by_run.setdefault(row.run_key, []).append(row)
        windows = [_window_view(run_rows) for _run, run_rows in sorted(by_run.items())]

        marker_counts = {"realId": 0, "missingId": 0}
        for item in items:
            if item["dedupeMarker"] == MARKER_REAL_ID:
                marker_counts["realId"] += 1
            else:
                marker_counts["missingId"] += 1

        result: dict[str, Any] = {
            "items": items,
            "total": int(total),
            "offset": offset,
            "windows": windows,
            "dedupeMarkers": marker_counts,
        }
        if offset + limit < total:
            result["nextCursor"] = _encode_cursor(offset + limit)
        return result


# ---------------------------------------------------------------------------
# Routes (companion push + operator query)
# ---------------------------------------------------------------------------

companion_router = APIRouter(prefix="/companion/v2/orders", tags=["fleet-orders-companion"])
operator_router = APIRouter(prefix="/api/v1/fleet/orders", tags=["fleet-orders-operator"])

BindingDep = Annotated[Any, Depends(binding)]
ActorDep = Annotated[Any, Depends(current_actor)]


def service(request: Request) -> FleetOrdersService:
    return cast(FleetOrdersService, request.app.state.fleet_orders_service)


ServiceDep = Annotated[FleetOrdersService, Depends(service)]


@companion_router.post("/screens")
async def push_order_screen(
    body: FleetOrderScreenIn,
    binding_row: BindingDep,
    fleet_orders: ServiceDep,
    response: Response,
) -> dict[str, Any]:
    result = await fleet_orders.push_screen(binding_row, body)
    response.status_code = status.HTTP_200_OK if result["replayed"] else status.HTTP_201_CREATED
    return result


@companion_router.get("/checkpoint")
async def get_order_checkpoint(
    binding_row: BindingDep,
    fleet_orders: ServiceDep,
    direction: Literal["SOLD", "BOUGHT"] = Query(),
) -> dict[str, Any]:
    return await fleet_orders.get_checkpoint(binding_row, direction)


@operator_router.get("/history")
async def fleet_order_history(
    actor: ActorDep,
    fleet_orders: ServiceDep,
    device_id: str | None = Query(default=None, max_length=36),
    direction: Literal["SOLD", "BOUGHT"] | None = Query(default=None),
    status_text: str | None = Query(default=None, max_length=64),
    account_key: str | None = Query(default=None, alias="account_key", max_length=128),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=256),
) -> dict[str, Any]:
    return await fleet_orders.history(
        actor,
        device_id=device_id,
        direction=direction,
        status_text=status_text,
        account_key=account_key,
        limit=limit,
        cursor=cursor,
    )


router = APIRouter()
router.include_router(companion_router)
router.include_router(operator_router)
