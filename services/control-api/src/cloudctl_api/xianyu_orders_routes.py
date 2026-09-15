"""Operator routes for xianyu order collection runs (order-sync/20260915.1 §6)."""

from __future__ import annotations

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Header, Request, Response, status

from .auth import current_actor
from .xianyu_orders import XianyuOrdersCollectRequest, XianyuOrdersService

router = APIRouter(prefix="/api/v1/xianyu/orders", tags=["xianyu-orders"])


def service(request: Request) -> XianyuOrdersService:
    return cast(XianyuOrdersService, request.app.state.xianyu_orders_service)


Service = Annotated[XianyuOrdersService, Depends(service)]
ActorDep = Annotated[Any, Depends(current_actor)]


@router.post(":collect")
async def collect_orders(
    body: XianyuOrdersCollectRequest,
    actor: ActorDep,
    orders: Service,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    result, created = await orders.run(actor, idempotency_key or "", body)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response.headers["Idempotency-Replayed"] = "false" if created else "true"
    return result


@router.get("/runs/{run_id}")
async def get_collection_run(run_id: str, actor: ActorDep, orders: Service) -> dict[str, Any]:
    return await orders.get_run(actor, run_id)
