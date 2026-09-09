"""Operator schedule routes for ONCE/RECURRING PlatformTask minting."""

from __future__ import annotations

from typing import Annotated, Any, cast

from cloudctl_domain import Actor
from fastapi import APIRouter, Depends, Request

from .auth import current_actor
from .schedules import ScheduleFireRequest, TaskScheduleCreate, TaskScheduleService

router = APIRouter(prefix="/api/v1/task-schedules", tags=["task-schedules"])
ActorDep = Annotated[Actor, Depends(current_actor)]


def service(request: Request) -> TaskScheduleService:
    return cast(TaskScheduleService, request.app.state.task_schedule_service)


Service = Annotated[TaskScheduleService, Depends(service)]


@router.post("", status_code=201)
async def create_schedule(
    body: TaskScheduleCreate, actor: ActorDep, schedules: Service
) -> dict[str, Any]:
    return await schedules.create(actor, body)


@router.get("")
async def list_schedules(actor: ActorDep, schedules: Service) -> list[dict[str, Any]]:
    return await schedules.list_schedules(actor)


@router.get("/{schedule_id}")
async def get_schedule(schedule_id: str, actor: ActorDep, schedules: Service) -> dict[str, Any]:
    return await schedules.get(actor, schedule_id)


@router.post("/{schedule_id}:enable")
async def enable_schedule(schedule_id: str, actor: ActorDep, schedules: Service) -> dict[str, Any]:
    return await schedules.set_enabled(actor, schedule_id, True)


@router.post("/{schedule_id}:disable")
async def disable_schedule(schedule_id: str, actor: ActorDep, schedules: Service) -> dict[str, Any]:
    return await schedules.set_enabled(actor, schedule_id, False)


@router.post("/{schedule_id}:fire")
async def fire_schedule(
    schedule_id: str,
    body: ScheduleFireRequest,
    actor: ActorDep,
    schedules: Service,
) -> dict[str, Any]:
    items = await schedules.fire(actor, schedule_id, body)
    return {"items": items, "count": len(items)}
