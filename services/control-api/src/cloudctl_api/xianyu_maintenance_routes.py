"""Operator routes for xianyu maintenance batch runs (p14 maintenance anchors)."""

from __future__ import annotations

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Header, Request, Response, status

from .auth import current_actor
from .xianyu_maintenance import XianyuMaintenanceRunRequest, XianyuMaintenanceService

router = APIRouter(prefix="/api/v1/xianyu", tags=["xianyu-maintenance"])


def service(request: Request) -> XianyuMaintenanceService:
    return cast(XianyuMaintenanceService, request.app.state.xianyu_maintenance_service)


Service = Annotated[XianyuMaintenanceService, Depends(service)]
ActorDep = Annotated[Any, Depends(current_actor)]


@router.post("/maintenance:run")
async def run_maintenance(
    body: XianyuMaintenanceRunRequest,
    actor: ActorDep,
    maintenance: Service,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    result, created = await maintenance.run(actor, idempotency_key or "", body)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response.headers["Idempotency-Replayed"] = "false" if created else "true"
    return result


@router.get("/maintenance/runs/{run_id}")
async def get_maintenance_run(
    run_id: str, actor: ActorDep, maintenance: Service
) -> dict[str, Any]:
    return await maintenance.get_run(actor, run_id)
