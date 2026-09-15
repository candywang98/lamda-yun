"""Order sync routes: companion push + operator query (order-sync/20260915.1)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .auth import current_actor
from .mobile_routes import binding
from .orders_service import MAX_BATCH, OrderService

companion_router = APIRouter(prefix="/companion/v2/orders", tags=["orders-companion"])
operator_router = APIRouter(prefix="/api/v1/orders", tags=["orders-operator"])

BindingDep = Annotated[Any, Depends(binding)]
ActorDep = Annotated[Any, Depends(current_actor)]


def service(request: Request) -> OrderService:
    return cast_service(request.app.state.orders_service)


def cast_service(value: object) -> OrderService:
    assert isinstance(value, OrderService)
    return value


Service = Annotated[OrderService, Depends(service)]


class OrderIn(BaseModel):
    """One collected order row; keys follow the frozen contract body (§3)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    direction: Literal["SOLD", "BOUGHT"]
    order_key: str = Field(min_length=1, max_length=256)
    item_title: str | None = Field(default=None, max_length=1024)
    buyer_name: str | None = Field(default=None, max_length=512)
    amount_cents: int | None = Field(default=None, gt=0)
    status_text: str | None = Field(default=None, max_length=256)
    occurred_at: str | None = Field(default=None, max_length=64)
    raw: dict[str, Any] | None = None

    @field_validator("order_key")
    @classmethod
    def order_key_is_usable(cls, value: str) -> str:
        # 宁缺勿假键: whitespace-only keys are rejected per row (422 with the
        # list index in the error location); real keys are trimmed and cut to
        # the 128-char column bound.
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("order_key must not be blank")
        return cleaned[:128]


class OrderBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    orders: list[OrderIn] = Field(min_length=1, max_length=MAX_BATCH)
    collected_at: str | None = Field(default=None, max_length=64)


@companion_router.post("/batch")
async def push_orders(
    body: OrderBatchIn, binding_row: BindingDep, orders: Service, response: Response
) -> dict[str, int]:
    result = await orders.ingest(binding_row, body.orders)
    # 201 when at least one row landed, 200 when the whole batch replayed.
    response.status_code = 201 if result["accepted"] else 200
    return result


@operator_router.get("")
async def list_orders(
    actor: ActorDep,
    orders: Service,
    device_id: str | None = Query(default=None, max_length=36),
    direction: Literal["SOLD", "BOUGHT"] | None = Query(default=None),
    status_text: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return await orders.list_orders(actor, device_id, direction, status_text, limit, offset)


@operator_router.get("/{order_id}")
async def get_order(order_id: str, actor: ActorDep, orders: Service) -> dict[str, Any]:
    return await orders.get_order(actor, order_id)
