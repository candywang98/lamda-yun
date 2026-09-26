"""Durable, task-bound order receipts, independent of the UI execution lease."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, cast

from cloudctl_domain import ConflictError, NotFoundError, ValidationError
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic import ValidationError as SchemaError
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .db import (
    AccountDeviceBindingRow,
    Base,
    Database,
    DeviceRow,
    MobileBindingRow,
    MobileTaskRow,
    OrderRow,
    PlatformAccountRow,
)
from .fleet_orders import FleetOrderPageRow, FleetOrderScreenIn, FleetOrdersService
from .mobile_routes import binding
from .mobile_service import _aware, _now
from .orders_service import parse_occurred_at

PROTOCOL = "order-delivery/1"
MAX_PAYLOAD_BYTES = 200_000


class OrderDeliveryReceiptRow(Base):
    __tablename__ = "order_delivery_receipt"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mobile_task.id"), index=True, nullable=False
    )
    device_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    screen: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    conflict_code: Mapped[str | None] = mapped_column(String(48))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "task_id", "kind", "screen", name="uq_order_delivery_receipt"
        ),
        CheckConstraint(
            "(kind = 'SCREEN' AND screen BETWEEN 1 AND 3) OR (kind = 'COMPLETE' AND screen = 0)",
            name="ck_order_delivery_kind_screen",
        ),
    )


class OrderDeliveryProjectionRow(Base):
    """Delivery provenance, without rewriting or guessing legacy row ownership."""

    __tablename__ = "order_delivery_projection"
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("xianyu_order.id"), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("mobile_task.id"), nullable=False)
    screen: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (CheckConstraint("screen BETWEEN 1 AND 3", name="ck_order_projection_screen"),)


class OrderDeliveryEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    protocol_version: Literal["order-delivery/1"] = Field(alias="protocolVersion")
    task_id: str = Field(alias="taskId", min_length=36, max_length=36)
    kind: Literal["SCREEN", "COMPLETE"]
    screen: int = Field(ge=0, le=3)
    payload_json: str = Field(alias="payloadJson", min_length=2, max_length=MAX_PAYLOAD_BYTES)
    payload_sha256: str = Field(alias="payloadSha256", pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_envelope(self) -> OrderDeliveryEnvelope:
        data = self.payload_json.encode("utf-8")
        if len(data) > MAX_PAYLOAD_BYTES:
            raise ValueError("order delivery payload exceeds byte limit")
        if hashlib.sha256(data).hexdigest() != self.payload_sha256:
            raise ValueError("order delivery payload digest mismatch")
        if (self.kind == "COMPLETE") != (self.screen == 0):
            raise ValueError("order delivery kind and ordinal do not match")
        return self


class OrderDeliveryComplete(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    run_key: str = Field(alias="runKey", min_length=36, max_length=36)
    account_key: str = Field(alias="accountKey", min_length=1, max_length=36)
    direction: Literal["SOLD", "BOUGHT"]
    total_screens: int = Field(alias="totalScreens", ge=1, le=3)
    stop_reason: Literal[
        "PLAN_FINISHED", "STOP_EMPTY_PAGE", "STOP_STAGNANT", "STOP_MAX_SCREENS"
    ] = Field(alias="stopReason")


def delivery_metadata(task: MobileTaskRow) -> dict[str, Any] | None:
    meta = ((task.steps or [{}])[0] or {}).get("orderCollection") or {}
    return meta if meta.get("deliveryProtocol") == PROTOCOL else None


async def delivery_identity_error(
    session: AsyncSession, task: MobileTaskRow, device: DeviceRow | None = None
) -> str | None:
    meta = delivery_metadata(task)
    if meta is None:
        return "ORDER_DELIVERY_PROTOCOL_REQUIRED"
    device = device or await session.get(DeviceRow, task.device_id)
    if device is None or device.active_binding_id != meta.get("mobileBindingId"):
        return "MOBILE_BINDING_CHANGED"
    live_mobile = await session.get(MobileBindingRow, device.active_binding_id)
    if live_mobile is None or live_mobile.revoked_at is not None:
        return "MOBILE_BINDING_CHANGED"
    account = await session.get(PlatformAccountRow, task.account_id) if task.account_id else None
    if (
        account is None
        or account.tenant_id != task.tenant_id
        or account.platform != "xianyu"
        or account.status != "AUTHORIZED"
        or account.revoked_at is not None
    ):
        return "ACCOUNT_BINDING_CHANGED"
    if account.expires_at is not None:
        if _aware(account.expires_at) <= _now():
            return "ACCOUNT_BINDING_CHANGED"
    bound = await session.scalar(
        select(AccountDeviceBindingRow).where(
            AccountDeviceBindingRow.tenant_id == task.tenant_id,
            AccountDeviceBindingRow.device_id == task.device_id,
            AccountDeviceBindingRow.account_id == task.account_id,
            AccountDeviceBindingRow.status == "BOUND",
        )
    )
    if bound is None or bound.binding_version != task.binding_version:
        return "ACCOUNT_BINDING_CHANGED"
    return None


async def resolve_order_account(
    session: AsyncSession, device: DeviceRow
) -> AccountDeviceBindingRow:
    if (device.capabilities or {}).get("orderDeliveryProtocol") != PROTOCOL:
        raise ConflictError("ORDER_DELIVERY_CAPABILITY_REQUIRED")
    mobile = (
        await session.get(MobileBindingRow, device.active_binding_id)
        if device.active_binding_id
        else None
    )
    if (
        mobile is None
        or mobile.revoked_at is not None
        or mobile.device_id != device.id
        or mobile.tenant_id != device.tenant_id
    ):
        raise ConflictError("MOBILE_BINDING_CHANGED")
    bindings = list(
        await session.scalars(
            select(AccountDeviceBindingRow)
            .where(
                AccountDeviceBindingRow.tenant_id == device.tenant_id,
                AccountDeviceBindingRow.device_id == device.id,
                AccountDeviceBindingRow.platform == "xianyu",
                AccountDeviceBindingRow.status == "BOUND",
            )
            .with_for_update()
        )
    )
    if len(bindings) != 1:
        raise ConflictError("ORDER_ACCOUNT_BINDING_REQUIRED")
    bound = bindings[0]
    account = await session.get(PlatformAccountRow, bound.account_id)
    if (
        account is None
        or account.tenant_id != device.tenant_id
        or account.platform != "xianyu"
        or account.status != "AUTHORIZED"
        or account.revoked_at is not None
        or (account.expires_at is not None and _aware(account.expires_at) <= _now())
    ):
        raise ConflictError("ACCOUNT_BINDING_CHANGED")
    return bound


async def order_delivery_view(session: AsyncSession, task: MobileTaskRow) -> dict[str, Any]:
    state = task.business_state or task.status
    result: dict[str, Any] = {
        "protocolVersion": None,
        "state": "LEGACY_UNVERIFIED",
        "receivedScreens": [],
        "expectedScreens": None,
        "collectionComplete": state == "SUCCEEDED",
        "stopReason": None,
    }
    if delivery_metadata(task) is None:
        return result
    receipts = list(
        await session.scalars(
            select(OrderDeliveryReceiptRow).where(
                OrderDeliveryReceiptRow.tenant_id == task.tenant_id,
                OrderDeliveryReceiptRow.task_id == task.id,
            )
        )
    )
    screens = sorted(row.screen for row in receipts if row.kind == "SCREEN")
    complete = next((row for row in receipts if row.kind == "COMPLETE"), None)
    final = OrderDeliveryComplete.model_validate_json(complete.payload_json) if complete else None
    reason = await delivery_identity_error(session, task)
    if not reason and any(row.conflict_code for row in receipts):
        reason = "PAYLOAD_CONFLICT"
    if not reason:
        reason = {
            "FAILED": "TASK_FAILED",
            "CANCELLED": "TASK_CANCELLED",
            "CANCELED": "TASK_CANCELLED",
            "EXPIRED": "TASK_EXPIRED",
            "RECONCILING": "COLLECTION_RECONCILING",
        }.get(state)
    synced = (
        final is not None
        and screens == list(range(1, final.total_screens + 1))
        and state == "SUCCEEDED"
    )
    return {
        **result,
        "protocolVersion": PROTOCOL,
        "state": "BLOCKED" if reason else "SYNCED" if synced else "PENDING",
        "receivedScreens": screens,
        "expectedScreens": final.total_screens if final else None,
        "stopReason": reason or (final.stop_reason if final else None),
    }


class OrderDeliveryService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.orders = FleetOrdersService(database)

    async def _upsert_observed_orders(
        self,
        session: AsyncSession,
        task: MobileTaskRow,
        payload: FleetOrderScreenIn,
        now: datetime,
    ) -> int:
        # Device locking serializes durable deliveries. Order by immutable
        # server-side collection generation, not arrival time or device clock.
        keys = {item.order_key.strip() for item in payload.rows}
        statement = select(OrderRow).where(
            OrderRow.tenant_id == task.tenant_id,
            OrderRow.device_id == task.device_id,
            OrderRow.platform == "xianyu",
            OrderRow.order_key.in_(keys),
        )
        existing = list(await session.scalars(statement))
        stale: set[str] = set()
        generation = (_aware(task.created_at), task.id, payload.screen)
        for order in existing:
            source = await session.get(OrderDeliveryProjectionRow, order.id)
            if source is None:
                continue
            prior_task = await session.get(MobileTaskRow, source.task_id)
            if prior_task is None:
                raise ConflictError("ORDER_PROJECTION_IDENTITY_MISSING")
            if (_aware(prior_task.created_at), prior_task.id, source.screen) > generation:
                stale.add(order.order_key)
        accepted_rows = [row for row in payload.rows if row.order_key.strip() not in stale]
        _, updated, _ = await self.orders._upsert_orders(
            session, task.tenant_id, task.device_id, accepted_rows, now
        )
        await session.flush()
        for order in await session.scalars(statement):
            if order.order_key in stale:
                continue
            source = await session.get(OrderDeliveryProjectionRow, order.id)
            if source is None:
                session.add(
                    OrderDeliveryProjectionRow(
                        order_id=order.id,
                        tenant_id=task.tenant_id,
                        task_id=task.id,
                        screen=payload.screen,
                    )
                )
            else:
                source.task_id = task.id
                source.screen = payload.screen
        return updated

    async def push(self, auth: MobileBindingRow, body: OrderDeliveryEnvelope) -> dict[str, Any]:
        conflict = False
        replayed = False
        async with self.database.unit_of_work() as session:
            device = await session.get(DeviceRow, auth.device_id, with_for_update=True)
            task = await session.get(MobileTaskRow, body.task_id, with_for_update=True)
            if (
                device is None
                or task is None
                or task.tenant_id != auth.tenant_id
                or task.device_id != auth.device_id
            ):
                raise NotFoundError("order collection task was not found")
            meta = delivery_metadata(task)
            reason = await delivery_identity_error(session, task, device)
            if reason or not meta or meta.get("mobileBindingId") != auth.id:
                raise ConflictError(reason or "MOBILE_BINDING_CHANGED")
            if task.started_at is None:
                raise ConflictError("ORDER_COLLECTION_NOT_STARTED")
            receipts = list(
                await session.scalars(
                    select(OrderDeliveryReceiptRow).where(
                        OrderDeliveryReceiptRow.tenant_id == auth.tenant_id,
                        OrderDeliveryReceiptRow.task_id == task.id,
                    )
                )
            )
            existing = next(
                (row for row in receipts if row.kind == body.kind and row.screen == body.screen),
                None,
            )
            if existing:
                if existing.payload_sha256 != body.payload_sha256:
                    existing.conflict_code = "PAYLOAD_CONFLICT"
                    conflict = True
                else:
                    replayed = True
            else:
                if any(row.conflict_code for row in receipts):
                    raise ConflictError("PAYLOAD_CONFLICT")
                try:
                    payload = (
                        FleetOrderScreenIn.model_validate_json(body.payload_json)
                        if body.kind == "SCREEN"
                        else OrderDeliveryComplete.model_validate_json(body.payload_json)
                    )
                except SchemaError as exc:
                    raise ValidationError("order delivery payload is invalid") from exc
                if (
                    payload.run_key != task.id
                    or payload.account_key != task.account_id
                    or payload.direction != meta["direction"]
                ):
                    raise ConflictError("ORDER_DELIVERY_IDENTITY_MISMATCH")
                bound = int(meta["screens"])
                if isinstance(payload, FleetOrderScreenIn):
                    if (
                        payload.screen != body.screen
                        or payload.screen > bound
                        or payload.schema_version != 1
                        or any(row.direction != payload.direction for row in payload.rows)
                        or payload.collected_at is None
                    ):
                        raise ConflictError("ORDER_DELIVERY_SCREEN_MISMATCH")
                elif payload.total_screens > bound:
                    raise ConflictError("ORDER_DELIVERY_SCREEN_MISMATCH")
                screens = sorted(row.screen for row in receipts if row.kind == "SCREEN")
                if any(row.kind == "COMPLETE" for row in receipts):
                    raise ConflictError("ORDER_DELIVERY_ALREADY_SEALED")
                now = _now()
                if isinstance(payload, FleetOrderScreenIn):
                    if screens != list(range(1, body.screen)):
                        raise ConflictError("ORDER_DELIVERY_SCREEN_GAP")
                    updated = await self._upsert_observed_orders(session, task, payload, now)
                    prior_keys = {
                        row.order_key
                        for receipt in receipts
                        if receipt.kind == "SCREEN"
                        for row in FleetOrderScreenIn.model_validate_json(receipt.payload_json).rows
                    }
                    keys = {row.order_key for row in payload.rows}
                    session.add(
                        FleetOrderPageRow(
                            id=str(uuid.uuid4()),
                            tenant_id=auth.tenant_id,
                            device_id=auth.device_id,
                            platform="xianyu",
                            direction=payload.direction,
                            account_key=payload.account_key,
                            run_key=task.id,
                            screen=body.screen,
                            rows_seen=len(payload.rows),
                            new_keys=len(keys - prior_keys),
                            updated_keys=updated,
                            overlap=len(payload.rows) - len(keys - prior_keys),
                            partial_rows=len(payload.partial_rows),
                            empty_page=not payload.rows,
                            collected_at=parse_occurred_at(payload.collected_at),
                            created_at=now,
                        )
                    )
                elif screens != list(range(1, payload.total_screens + 1)):
                    raise ConflictError("ORDER_DELIVERY_INCOMPLETE")
                session.add(
                    OrderDeliveryReceiptRow(
                        id=str(uuid.uuid4()),
                        tenant_id=auth.tenant_id,
                        task_id=task.id,
                        device_id=auth.device_id,
                        kind=body.kind,
                        screen=body.screen,
                        payload_sha256=body.payload_sha256,
                        payload_json=body.payload_json,
                        conflict_code=None,
                        created_at=now,
                    )
                )
        # Commit the conflict indicator before reporting rejection.
        if conflict:
            raise ConflictError("PAYLOAD_CONFLICT")
        return {
            "protocolVersion": PROTOCOL,
            "taskId": body.task_id,
            "kind": body.kind,
            "screen": body.screen,
            "payloadSha256": body.payload_sha256,
            "accepted": True,
            "replayed": replayed,
        }


router = APIRouter(prefix="/companion/v2/orders", tags=["orders"])
Binding = Annotated[MobileBindingRow, Depends(binding)]


def service(request: Request) -> OrderDeliveryService:
    return cast(OrderDeliveryService, request.app.state.order_delivery_service)


@router.post("/delivery")
async def deliver_orders(
    body: OrderDeliveryEnvelope,
    auth: Binding,
    orders: Annotated[OrderDeliveryService, Depends(service)],
    response: Response,
) -> dict[str, Any]:
    result = await orders.push(auth, body)
    response.status_code = 200 if result["replayed"] else 201
    return result
