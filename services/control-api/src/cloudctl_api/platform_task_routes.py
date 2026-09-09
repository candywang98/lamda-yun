"""Operator PlatformTask routes. MobileTask remains the runner queue."""

from __future__ import annotations

from typing import Annotated, Any, cast

from cloudctl_domain import Actor
from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from .auth import current_actor
from .platform_tasks import (
    PlatformTaskCreate,
    PlatformTaskPause,
    PlatformTaskReconcile,
    PlatformTaskResume,
    PlatformTaskRetry,
    PlatformTaskService,
)

router = APIRouter(prefix="/api/v1/platform-tasks", tags=["platform-tasks"])
ActorDep = Annotated[Actor, Depends(current_actor)]


def service(request: Request) -> PlatformTaskService:
    return cast(PlatformTaskService, request.app.state.platform_task_service)


Service = Annotated[PlatformTaskService, Depends(service)]


@router.post("")
async def create_platform_tasks(
    body: PlatformTaskCreate,
    actor: ActorDep,
    platform: Service,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    items, created = await platform.create(actor, idempotency_key or "", body)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response.headers["Idempotency-Replayed"] = "false" if created else "true"
    return {"items": items, "count": len(items)}


@router.get("")
async def list_platform_tasks(
    actor: ActorDep,
    platform: Service,
    after: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    device_id: str | None = Query(default=None, alias="deviceId"),
    batch_id: str | None = Query(default=None, alias="batchId"),
    state: str | None = None,
) -> dict[str, Any]:
    return await platform.list_tasks(
        actor,
        after=after,
        limit=limit,
        device_id=device_id,
        batch_id=batch_id,
        state=state,
    )


@router.get("/{task_id}")
async def get_platform_task(task_id: str, actor: ActorDep, platform: Service) -> dict[str, Any]:
    return await platform.get(actor, task_id)


@router.post("/{task_id}:cancel")
async def cancel_platform_task(
    task_id: str,
    actor: ActorDep,
    platform: Service,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reason = "operator canceled"
    if isinstance(body, dict) and isinstance(body.get("reason"), str) and body["reason"].strip():
        reason = body["reason"].strip()
    return await platform.cancel(actor, task_id, reason)


@router.post("/{task_id}:retry")
async def retry_platform_task(
    task_id: str,
    body: PlatformTaskRetry,
    actor: ActorDep,
    platform: Service,
) -> dict[str, Any]:
    return await platform.retry(actor, task_id, body)


@router.post("/{task_id}:pause")
async def pause_platform_task(
    task_id: str,
    body: PlatformTaskPause,
    actor: ActorDep,
    platform: Service,
) -> dict[str, Any]:
    return await platform.pause(actor, task_id, body.reason)


@router.post("/{task_id}:ack-paused")
async def ack_paused_platform_task(
    task_id: str,
    actor: ActorDep,
    platform: Service,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lease_id = body.get("leaseId") if isinstance(body, dict) else None
    return await platform.ack_paused(task_id, lease_id if isinstance(lease_id, str) else None)


@router.post("/{task_id}:resume")
async def resume_platform_task(
    task_id: str,
    body: PlatformTaskResume,
    actor: ActorDep,
    platform: Service,
) -> dict[str, Any]:
    return await platform.resume(actor, task_id, body)


@router.post("/{task_id}:mark-unknown")
async def mark_unknown_platform_task(
    task_id: str,
    actor: ActorDep,
    platform: Service,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reason = "commit result unknown"
    if isinstance(body, dict) and isinstance(body.get("reason"), str) and body["reason"].strip():
        reason = body["reason"].strip()
    return await platform.mark_unknown(actor, task_id, reason)


@router.post("/{task_id}:reconcile")
async def reconcile_platform_task(
    task_id: str,
    body: PlatformTaskReconcile,
    actor: ActorDep,
    platform: Service,
) -> dict[str, Any]:
    return await platform.reconcile(actor, task_id, body)
