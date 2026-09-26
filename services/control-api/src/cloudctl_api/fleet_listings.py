"""Fleet listing collection: identity dedupe + change history (P43/P44 slice).

The xy-tasks-24 「采集宝贝信息」 fleet layer, modeled on the O10 order-sync
shape (``fleet_orders``) but leaner — listings have no direction and no
cross-screen checkpoint; their identity IS the dedupe dimension:

- ``fleet_listing``          — ONE row per (tenant, device, platform,
  item_key). ``item_key`` is the controller-ruled composite natural key
  ``{title}|{price_cents}`` (same cleaning rules as order-sync slice 1:
  strip U+200B/outer whitespace, title cap 64, whole key cap 128) — the
  Xianyu 「我发布的」 list page exposes no platform item id, and a fabricated
  one is never acceptable. First-write-wins identity; later screens UPSERT
  the mutable snapshot fields (title/price/status) and bump last_seen.
- ``fleet_listing_snapshot`` — append-only change history: a snapshot row is
  inserted ONLY when the content hash of the parsed row changes, so 「宝贝
  流量变化/价格变化」 is queryable without re-reading every screen.
- ``fleet_listing_screen``   — page guard, unique (tenant, device, run_key,
  screen): an offline replay of the same screen stores exactly one page and
  never double-counts.

Read-only invariant: this module records observed rows only — no step
builders, no ledger-gated clicks, no publishing implications.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from typing import Annotated, Any, cast

from cloudctl_domain import NotFoundError
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
from sqlalchemy.orm import Mapped, mapped_column

from .auth import current_actor
from .db import Base, Database, DeviceRow, TimestampMixin
from .mobile_routes import binding
from .mobile_service import _now

PLATFORM = "xianyu"
ITEM_KEY_MAX = 128
TITLE_MAX = 64
STATUS_MAX = 64
MAX_ROWS = 60

_DIGIT_RUN = re.compile(r"^\d{15,24}$")


# ---------------------------------------------------------------------------
# ORM rows (shared Base metadata; SQL migration 20260920_0030)
# ---------------------------------------------------------------------------


class FleetListingRow(Base, TimestampMixin):
    """Latest state of one collected listing identity per device."""

    __tablename__ = "fleet_listing"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "device_id", "platform", "item_key", name="uq_fleet_listing_identity"
        ),
        CheckConstraint("price_cents is null or price_cents >= 0", name="ck_fleet_listing_price"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("device.id"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(16), nullable=False, default=PLATFORM)
    item_key: Mapped[str] = mapped_column(String(ITEM_KEY_MAX), nullable=False)
    dedupe_marker: Mapped[str] = mapped_column(String(16), nullable=False, default="MISSING_ID")
    title: Mapped[str | None] = mapped_column(String(TITLE_MAX))
    price_cents: Mapped[int | None] = mapped_column(Integer)
    price_text: Mapped[str | None] = mapped_column(String(32))
    status_text: Mapped[str | None] = mapped_column(String(STATUS_MAX))
    exposure_count: Mapped[int | None] = mapped_column(Integer)
    views_count: Mapped[int | None] = mapped_column(Integer)
    wants_count: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FleetListingSnapshotRow(Base, TimestampMixin):
    """Append-only history: inserted only when the parsed content changes."""

    __tablename__ = "fleet_listing_snapshot"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    item_key: Mapped[str] = mapped_column(String(ITEM_KEY_MAX), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(String(4096), nullable=False)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FleetListingScreenRow(Base, TimestampMixin):
    """One collected screen per (tenant, device, run, screen) — replay guard."""

    __tablename__ = "fleet_listing_screen"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "device_id", "run_key", "screen", name="uq_fleet_listing_screen"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(16), nullable=False, default=PLATFORM)
    run_key: Mapped[str] = mapped_column(String(64), nullable=False)
    screen: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_keys: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_keys: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    partial_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    empty_page: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# IO models
# ---------------------------------------------------------------------------


class ListingRowIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_key: str = Field(min_length=1, max_length=ITEM_KEY_MAX)
    title: str | None = Field(default=None, max_length=256)
    price_cents: int | None = Field(default=None, ge=0)
    price_text: str | None = Field(default=None, max_length=32)
    status_text: str | None = Field(default=None, max_length=STATUS_MAX)
    exposure_count: int | None = Field(default=None, ge=0)
    views_count: int | None = Field(default=None, ge=0)
    wants_count: int | None = Field(default=None, ge=0)


class FleetListingScreenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1, max_length=32)
    run_key: str = Field(min_length=1, max_length=64)
    screen: int = Field(ge=1, le=200)
    collected_at: str | None = Field(default=None, max_length=40)
    rows: list[ListingRowIn] = Field(default_factory=list, max_length=MAX_ROWS)
    partial_rows: int = Field(default=0, ge=0, le=MAX_ROWS)


def _parse_collected_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _row_hash(row: ListingRowIn) -> str:
    payload = json.dumps(
        {
            "title": row.title,
            "price_cents": row.price_cents,
            "price_text": row.price_text,
            "status_text": row.status_text,
            "exposure_count": row.exposure_count,
            "views_count": row.views_count,
            "wants_count": row.wants_count,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _listing_view(row: FleetListingRow) -> dict[str, Any]:
    return {
        "itemKey": row.item_key,
        "dedupeMarker": row.dedupe_marker,
        "title": row.title,
        "priceCents": row.price_cents,
        "priceText": row.price_text,
        "statusText": row.status_text,
        "exposureCount": row.exposure_count,
        "viewsCount": row.views_count,
        "wantsCount": row.wants_count,
        "snapshotCount": row.snapshot_count,
        "firstSeenAt": row.first_seen_at,
        "lastSeenAt": row.last_seen_at,
    }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class FleetListingsService:
    """Screen push (identity dedupe-upsert + change history) and listing query."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def push_screen(self, binding_row: Any, body: FleetListingScreenIn) -> dict[str, Any]:
        tenant_id = binding_row.tenant_id
        device_id = binding_row.device_id
        now = _now()
        collected_at = _parse_collected_at(body.collected_at)
        async with self.database.unit_of_work() as session:
            device = await session.get(DeviceRow, device_id)
            if device is None or device.tenant_id != tenant_id:
                raise NotFoundError("device was not found")

            screen_row = await session.scalar(
                select(FleetListingScreenRow).where(
                    FleetListingScreenRow.tenant_id == tenant_id,
                    FleetListingScreenRow.device_id == device_id,
                    FleetListingScreenRow.run_key == body.run_key,
                    FleetListingScreenRow.screen == body.screen,
                )
            )
            if screen_row is not None:
                # 断网重传：同屏重放不重复计数、不追加历史。
                return {
                    "accepted": 0,
                    "updated": 0,
                    "duplicates": len(body.rows),
                    "screen": body.screen,
                    "replayed": True,
                }

            accepted = updated = duplicates = 0
            for row in body.rows:
                content_hash = _row_hash(row)
                existing = await session.scalar(
                    select(FleetListingRow).where(
                        FleetListingRow.tenant_id == tenant_id,
                        FleetListingRow.device_id == device_id,
                        FleetListingRow.platform == PLATFORM,
                        FleetListingRow.item_key == row.item_key,
                    )
                )
                if existing is None:
                    session.add(
                        FleetListingRow(
                            id=str(uuid.uuid4()),
                            tenant_id=tenant_id,
                            device_id=device_id,
                            platform=PLATFORM,
                            item_key=row.item_key,
                            dedupe_marker=(
                                "REAL_ID" if _DIGIT_RUN.match(row.item_key) else "MISSING_ID"
                            ),
                            title=row.title,
                            price_cents=row.price_cents,
                            price_text=row.price_text,
                            status_text=row.status_text,
                            exposure_count=row.exposure_count,
                            views_count=row.views_count,
                            wants_count=row.wants_count,
                            content_hash=content_hash,
                            snapshot_count=1,
                            first_seen_at=now,
                            last_seen_at=now,
                            created_at=now,
                        )
                    )
                    session.add(
                        FleetListingSnapshotRow(
                            id=str(uuid.uuid4()),
                            tenant_id=tenant_id,
                            device_id=device_id,
                            item_key=row.item_key,
                            content_hash=content_hash,
                            snapshot_json=json.dumps(
                                {
                                    "title": row.title,
                                    "priceCents": row.price_cents,
                                    "priceText": row.price_text,
                                    "statusText": row.status_text,
                                    "exposureCount": row.exposure_count,
                                    "viewsCount": row.views_count,
                                    "wantsCount": row.wants_count,
                                },
                                ensure_ascii=False,
                            ),
                            collected_at=collected_at,
                            created_at=now,
                        )
                    )
                    accepted += 1
                elif existing.content_hash != content_hash:
                    existing.title = row.title
                    existing.price_cents = row.price_cents
                    existing.price_text = row.price_text
                    existing.status_text = row.status_text
                    existing.exposure_count = row.exposure_count
                    existing.views_count = row.views_count
                    existing.wants_count = row.wants_count
                    existing.content_hash = content_hash
                    existing.snapshot_count += 1
                    existing.last_seen_at = now
                    session.add(
                        FleetListingSnapshotRow(
                            id=str(uuid.uuid4()),
                            tenant_id=tenant_id,
                            device_id=device_id,
                            item_key=row.item_key,
                            content_hash=content_hash,
                            snapshot_json=json.dumps(
                                {
                                    "title": row.title,
                                    "priceCents": row.price_cents,
                                    "priceText": row.price_text,
                                    "statusText": row.status_text,
                                    "exposureCount": row.exposure_count,
                                    "viewsCount": row.views_count,
                                    "wantsCount": row.wants_count,
                                },
                                ensure_ascii=False,
                            ),
                            collected_at=collected_at,
                            created_at=now,
                        )
                    )
                    updated += 1
                else:
                    existing.last_seen_at = now
                    duplicates += 1

            session.add(
                FleetListingScreenRow(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    device_id=device_id,
                    platform=PLATFORM,
                    run_key=body.run_key,
                    screen=body.screen,
                    rows_seen=len(body.rows),
                    new_keys=accepted,
                    updated_keys=updated,
                    duplicates=duplicates,
                    partial_rows=body.partial_rows,
                    empty_page=len(body.rows) == 0,
                    collected_at=collected_at,
                    created_at=now,
                )
            )
            await session.flush()
            return {
                "accepted": accepted,
                "updated": updated,
                "duplicates": duplicates,
                "screen": body.screen,
                "replayed": False,
            }

    async def listing_history(
        self,
        actor: Any,
        *,
        device_id: str | None,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        offset = 0
        if cursor:
            try:
                offset = max(0, int(cursor))
            except ValueError:
                offset = 0
        async with self.database.unit_of_work() as session:
            conditions = [FleetListingRow.tenant_id == str(actor.tenant_id)]
            if device_id:
                conditions.append(FleetListingRow.device_id == device_id)
            rows = list(
                await session.scalars(
                    select(FleetListingRow)
                    .where(*conditions)
                    .order_by(FleetListingRow.last_seen_at.desc(), FleetListingRow.item_key)
                    .offset(offset)
                    .limit(limit + 1)
                )
            )
            total = await session.scalar(
                select(func.count()).select_from(FleetListingRow).where(*conditions)
            )
        has_more = len(rows) > limit
        items = [_listing_view(row) for row in rows[:limit]]
        return {
            "items": items,
            "total": int(total or 0),
            "nextCursor": str(offset + limit) if has_more else None,
        }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

companion_router = APIRouter(prefix="/companion/v2/fleet/listings", tags=["fleet-listings"])
operator_router = APIRouter(prefix="/api/v1/fleet/listings", tags=["fleet-listings"])


def service(request: Request) -> FleetListingsService:
    return cast(FleetListingsService, request.app.state.fleet_listings_service)


ServiceDep = Annotated[FleetListingsService, Depends(service)]
BindingDep = Annotated[Any, Depends(binding)]
ActorDep = Annotated[Any, Depends(current_actor)]


@companion_router.post("/screens")
async def push_listing_screen(
    body: FleetListingScreenIn,
    binding_row: BindingDep,
    fleet_listings: ServiceDep,
    response: Response,
) -> dict[str, Any]:
    result = await fleet_listings.push_screen(binding_row, body)
    response.status_code = status.HTTP_200_OK if result["replayed"] else status.HTTP_201_CREATED
    return result


@operator_router.get("/history")
async def fleet_listing_history(
    actor: ActorDep,
    fleet_listings: ServiceDep,
    device_id: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=16),
) -> dict[str, Any]:
    return await fleet_listings.listing_history(
        actor, device_id=device_id, limit=limit, cursor=cursor
    )


router = APIRouter()
router.include_router(companion_router)
router.include_router(operator_router)
