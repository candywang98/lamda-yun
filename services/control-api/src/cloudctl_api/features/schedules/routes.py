"""F12 fleet schedule routes: worker tick surface + terminal cancel.

The mint/poll endpoints are the temporal-worker's service-to-service surface
(same auth model as every other operator route — the worker calls with its
service actor headers). Cancel is the operator-facing F12 §4 semantics.
"""

from __future__ import annotations

from typing import Annotated, Any, cast

from cloudctl_domain import Actor
from fastapi import APIRouter, Depends, Request, Response, status

from ...auth import current_actor
from .schemas import (
    FleetScheduleCancelRequest,
    FleetScheduleMintRequest,
    FleetSchedulePollRequest,
)
from .service import FleetScheduleService

router = APIRouter(prefix="/api/v1/fleet-schedules", tags=["fleet-schedules"])
ActorDep = Annotated[Actor, Depends(current_actor)]


def service(request: Request) -> FleetScheduleService:
    return cast(FleetScheduleService, request.app.state.fleet_schedule_service)


Service = Annotated[FleetScheduleService, Depends(service)]


@router.post(":poll")
async def poll_due_schedules(
    body: FleetSchedulePollRequest, actor: ActorDep, schedules: Service
) -> dict[str, Any]:
    return await schedules.poll_due(actor, now=body.now)


@router.post("/{schedule_id}:mint-due")
async def mint_due(
    schedule_id: str,
    body: FleetScheduleMintRequest,
    actor: ActorDep,
    schedules: Service,
    response: Response,
) -> dict[str, Any]:
    result = await schedules.mint_due(actor, schedule_id, now=body.now)
    # A04 semantics: first mint answers 201, a replayed tick (same period,
    # same fire key) answers 200 and is marked as an idempotent replay.
    response.status_code = (
        status.HTTP_201_CREATED if result["createdAny"] else status.HTTP_200_OK
    )
    response.headers["Idempotency-Replayed"] = "false" if result["createdAny"] else "true"
    return result


@router.post("/{schedule_id}:cancel")
async def cancel_schedule(
    schedule_id: str,
    body: FleetScheduleCancelRequest,
    actor: ActorDep,
    schedules: Service,
) -> dict[str, Any]:
    return await schedules.cancel(actor, schedule_id, body.reason)
