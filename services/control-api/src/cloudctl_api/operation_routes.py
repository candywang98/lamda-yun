"""HTTP routes for the 15-module asynchronous operation catalog."""

from __future__ import annotations

from typing import Annotated, Any, cast

from cloudctl_domain import Actor
from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from .auth import current_actor
from .operation_schemas import (
    BatchOperationCreate,
    OperationApprovalRequest,
    OperationAuditResultView,
    OperationCancelRequest,
    OperationCatalogView,
    OperationFeatureConfigDraftPut,
    OperationFeatureConfigDraftView,
    OperationFeatureView,
    OperationItemResultUpdate,
    OperationTaskCreate,
    OperationTaskSummaryView,
    OperationTaskView,
)
from .operation_service import OperationService

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])
ActorDependency = Annotated[Actor, Depends(current_actor)]


def service(request: Request) -> OperationService:
    return cast(OperationService, request.app.state.operation_service)


ServiceDependency = Annotated[OperationService, Depends(service)]


@router.get("/catalog", response_model=list[OperationCatalogView])
async def operation_catalog(
    actor: ActorDependency, operations: ServiceDependency
) -> list[dict[str, Any]]:
    return operations.catalog(actor)


@router.get("/features", response_model=list[OperationFeatureView])
async def operation_features(
    actor: ActorDependency, operations: ServiceDependency
) -> list[dict[str, Any]]:
    return operations.features(actor)


@router.get(
    "/features/{feature_id}/config-draft",
    response_model=OperationFeatureConfigDraftView,
)
async def get_operation_feature_config_draft(
    feature_id: str,
    actor: ActorDependency,
    operations: ServiceDependency,
) -> dict[str, Any]:
    return await operations.get_feature_config_draft(actor, feature_id)


@router.put(
    "/features/{feature_id}/config-draft",
    response_model=OperationFeatureConfigDraftView,
)
async def put_operation_feature_config_draft(
    feature_id: str,
    body: OperationFeatureConfigDraftPut,
    actor: ActorDependency,
    operations: ServiceDependency,
) -> dict[str, Any]:
    return await operations.put_feature_config_draft(actor, feature_id, body)


@router.get("/tasks", response_model=list[OperationTaskSummaryView])
async def list_operation_tasks(
    actor: ActorDependency,
    operations: ServiceDependency,
    module: str | None = None,
    task_status: Annotated[str | None, Query(alias="status")] = None,
    after_id: Annotated[str | None, Query(alias="afterId")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[dict[str, Any]]:
    return await operations.list_tasks(
        actor,
        module=module,
        status=task_status,
        after_id=after_id,
        limit=limit,
    )


@router.post("/tasks", response_model=OperationTaskView)
async def create_operation_task(
    body: OperationTaskCreate,
    actor: ActorDependency,
    operations: ServiceDependency,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    result, created = await operations.create_task(
        actor,
        idempotency_key=idempotency_key or "",
        operation_key=body.operation_key,
        feature_id=body.feature_id,
        resource_ids=[body.resource_id],
        parameters=body.parameters,
        context=body.context,
        is_batch=False,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response.headers["Idempotency-Replayed"] = "false" if created else "true"
    return result


@router.post(":batch", response_model=OperationTaskView)
async def create_batch_operation(
    body: BatchOperationCreate,
    actor: ActorDependency,
    operations: ServiceDependency,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    result, created = await operations.create_task(
        actor,
        idempotency_key=idempotency_key or "",
        operation_key=body.operation_key,
        feature_id=body.feature_id,
        resource_ids=body.resource_ids,
        parameters=body.parameters,
        context=body.context,
        is_batch=True,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response.headers["Idempotency-Replayed"] = "false" if created else "true"
    return result


@router.get("/tasks/{task_id}", response_model=OperationTaskView)
async def get_operation_task(
    task_id: str, actor: ActorDependency, operations: ServiceDependency
) -> dict[str, Any]:
    return await operations.get_task(actor, task_id)


@router.post(
    "/tasks/{task_id}/items/{resource_id}:result",
    response_model=OperationTaskView,
)
async def record_operation_item_result(
    task_id: str,
    resource_id: str,
    body: OperationItemResultUpdate,
    actor: ActorDependency,
    operations: ServiceDependency,
) -> dict[str, Any]:
    return await operations.record_item_result(actor, task_id, resource_id, body)


@router.post("/tasks/{task_id}:cancel", response_model=OperationTaskView)
async def cancel_operation_task(
    task_id: str,
    body: OperationCancelRequest,
    actor: ActorDependency,
    operations: ServiceDependency,
) -> dict[str, Any]:
    return await operations.cancel_task(actor, task_id, body.reason)


@router.post("/tasks/{task_id}:approve", response_model=OperationTaskView)
async def approve_operation_task(
    task_id: str,
    body: OperationApprovalRequest,
    actor: ActorDependency,
    operations: ServiceDependency,
) -> dict[str, Any]:
    return await operations.decide_task(actor, task_id, approved=True, reason=body.reason)


@router.post("/tasks/{task_id}:reject", response_model=OperationTaskView)
async def reject_operation_task(
    task_id: str,
    body: OperationApprovalRequest,
    actor: ActorDependency,
    operations: ServiceDependency,
) -> dict[str, Any]:
    return await operations.decide_task(actor, task_id, approved=False, reason=body.reason)


@router.get("/tasks/{task_id}/audit-result", response_model=OperationAuditResultView)
async def operation_audit_result(
    task_id: str, actor: ActorDependency, operations: ServiceDependency
) -> dict[str, Any]:
    return await operations.audit_result(actor, task_id)
