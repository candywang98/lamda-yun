"""Versioned REST and server-sent event routes."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any, cast

from cloudctl_domain import Actor, Permission, PublishState, require_permissions
from cloudctl_domain.rbac import ROLE_PERMISSIONS
from fastapi import APIRouter, Body, Depends, Header, Query, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from .auth import current_actor
from .schemas import (
    AccountDeviceBind,
    AccountStatusUpdate,
    ApkArtifactCreate,
    ApprovalRequest,
    AutomationPackageCreate,
    AutomationPromotionRequest,
    CommitIntentCreate,
    ContentArchiveRequest,
    ContentCreate,
    ContentGroupCreate,
    ContentGroupMembershipCreate,
    ContentXianyuDispatchRequest,
    DeviceCreate,
    EdgeCreate,
    LeaseRequest,
    MaintenanceRequest,
    MediaCreate,
    MediaDerivativeCreate,
    MediaDerivativeResult,
    MediaGroupUpdate,
    MediaTaxonomyUpdate,
    MediaUploadComplete,
    MediaUploadCreate,
    PlatformAccountCreate,
    ProductArchiveRequest,
    ProductBatchDelete,
    ProductBatchUpdateGroup,
    ProductBatchUpdatePrice,
    ProductCreate,
    ProductFilterRequest,
    ProductImportRequest,
    ProductMediaUpdate,
    ProductUpdate,
    PublishPlanCreate,
    RecipePublishRequest,
    RecipeRollbackRequest,
    RevisionCreate,
    RoleUpdate,
    TargetStateUpdate,
    TenantCreate,
    UserCreate,
)
from .services import ControlService
from .settings import Settings, get_settings

router = APIRouter(prefix="/api/v1")
ActorDependency = Annotated[Actor, Depends(current_actor)]


def service(request: Request) -> ControlService:
    return cast(ControlService, request.app.state.control_service)


ServiceDependency = Annotated[ControlService, Depends(service)]


@router.get("/session")
async def session_info(actor: ActorDependency) -> dict[str, Any]:
    return {
        "tenantId": str(actor.tenant_id),
        "userId": str(actor.user_id),
        "roles": sorted(role.value for role in actor.roles),
        "mfa": actor.mfa,
        "requestId": actor.request_id,
    }


@router.post("/tenants", status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate, actor: ActorDependency, control: ServiceDependency
) -> dict[str, Any]:
    return await control.create_tenant(actor, body.name)


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate, actor: ActorDependency, control: ServiceDependency
) -> dict[str, Any]:
    return await control.create_user(actor, body)


@router.put("/users/{user_id}/roles")
async def update_user_roles(
    user_id: str,
    body: RoleUpdate,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.update_user_roles(actor, user_id, body)


@router.get("/settings/security-policy")
async def security_policy(
    actor: ActorDependency,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    require_permissions(actor.roles, Permission.TENANT_ADMIN)
    return {
        "environment": settings.env,
        "repositoryMode": settings.repository_mode,
        "oidcIssuer": settings.oidc_issuer,
        "oidcAudience": settings.oidc_audience,
        "developmentAuthBypass": settings.dev_auth_bypass,
        "roles": {
            role.value: sorted(permission.value for permission in permissions)
            for role, permissions in ROLE_PERMISSIONS.items()
        },
        "productionForbiddenCapabilities": [
            "adb.remote",
            "frida",
            "mitm",
            "proxy.mutate",
            "shell.arbitrary",
        ],
    }


@router.post("/edges", status_code=status.HTTP_201_CREATED)
async def create_edge(
    body: EdgeCreate, actor: ActorDependency, control: ServiceDependency
) -> dict[str, Any]:
    return await control.create_edge(actor, body)


@router.post("/devices", status_code=status.HTTP_201_CREATED)
async def create_device(
    body: DeviceCreate, actor: ActorDependency, control: ServiceDependency
) -> dict[str, Any]:
    return await control.create_device(actor, body)


@router.get("/devices")
async def list_devices(actor: ActorDependency, control: ServiceDependency) -> list[dict[str, Any]]:
    return await control.list_devices(actor)


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
async def create_platform_account(
    body: PlatformAccountCreate,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.create_platform_account(actor, body)


@router.get("/accounts")
async def list_platform_accounts(
    actor: ActorDependency, control: ServiceDependency
) -> list[dict[str, Any]]:
    return await control.list_platform_accounts(actor)


@router.get("/accounts/{account_id}/ownership")
async def get_account_ownership(
    account_id: str,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.get_account_ownership(actor, account_id)


@router.post("/accounts/{account_id}/bindings", status_code=status.HTTP_201_CREATED)
async def bind_account_device(
    account_id: str,
    body: AccountDeviceBind,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.bind_account_device(actor, account_id, body)


@router.delete("/accounts/{account_id}/bindings/{device_id}", status_code=204)
async def unbind_account_device(
    account_id: str,
    device_id: str,
    actor: ActorDependency,
    control: ServiceDependency,
) -> Response:
    await control.unbind_account_device(actor, account_id, device_id)
    return Response(status_code=204)


@router.post("/accounts/{account_id}:status")
async def update_account_status(
    account_id: str,
    body: AccountStatusUpdate,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.update_account_status(actor, account_id, body)


@router.post("/devices/{device_id}:maintenance")
async def set_device_maintenance(
    device_id: str,
    body: MaintenanceRequest,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.set_maintenance(actor, device_id, body)


@router.post("/devices/{device_id}/leases", status_code=status.HTTP_201_CREATED)
async def acquire_device_lease(
    device_id: str,
    body: LeaseRequest,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.acquire_lease(actor, device_id, body.owner_workflow_id, body.ttl_seconds)


@router.delete("/devices/{device_id}/leases/{lease_id}", status_code=status.HTTP_204_NO_CONTENT)
async def release_device_lease(
    device_id: str,
    lease_id: str,
    actor: ActorDependency,
    control: ServiceDependency,
) -> Response:
    await control.release_lease(actor, device_id, lease_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/media/uploads", status_code=status.HTTP_201_CREATED)
async def initiate_media_upload(
    body: MediaUploadCreate, actor: ActorDependency, control: ServiceDependency
) -> dict[str, Any]:
    return await control.initiate_media_upload(actor, body)


@router.put("/media/assets/{asset_id}/taxonomy")
async def update_media_taxonomy(
    asset_id: str, body: MediaTaxonomyUpdate, actor: ActorDependency, control: ServiceDependency
) -> dict[str, Any]:
    return await control.update_media_taxonomy(actor, asset_id, body)


@router.get("/media/assets/{asset_id}/references")
async def media_references(
    asset_id: str, actor: ActorDependency, control: ServiceDependency
) -> dict[str, Any]:
    return await control.get_media_references(actor, asset_id)


@router.get("/media/assets/{asset_id}/content")
async def download_media_asset_content(
    asset_id: str, actor: ActorDependency, control: ServiceDependency
) -> Response:
    content, content_type = await control.download_media_asset(actor, asset_id)
    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/media/assets")
async def list_media_assets(
    actor: ActorDependency,
    control: ServiceDependency,
    tag: Annotated[str | None, Query()] = None,
    group_id: Annotated[str | None, Query(alias="groupId")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
) -> dict[str, Any]:
    return await control.list_media_assets(
        actor, tag=tag, group_id=group_id, page=page, page_size=page_size
    )


@router.post("/media-groups", status_code=status.HTTP_201_CREATED)
async def create_media_group(
    body: ContentGroupCreate, actor: ActorDependency, control: ServiceDependency
) -> dict[str, Any]:
    return await control.create_media_group(actor, body)


@router.get("/media-groups")
async def list_media_groups(
    actor: ActorDependency, control: ServiceDependency
) -> list[dict[str, Any]]:
    return await control.list_media_groups(actor)


@router.put("/media-groups/{group_id}")
async def update_media_group(
    group_id: str,
    body: MediaGroupUpdate,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.update_media_group(actor, group_id, body)


@router.delete("/media-groups/{group_id}", status_code=204)
async def delete_media_group(
    group_id: str, actor: ActorDependency, control: ServiceDependency
) -> Response:
    await control.delete_media_group(actor, group_id)
    return Response(status_code=204)


@router.post("/products", status_code=status.HTTP_201_CREATED)
async def create_product(
    body: ProductCreate, actor: ActorDependency, control: ServiceDependency
) -> dict[str, Any]:
    return await control.create_product(actor, body)


@router.get("/products")
async def list_products(actor: ActorDependency, control: ServiceDependency) -> list[dict[str, Any]]:
    return await control.list_products(actor)


@router.get("/products/{product_id}")
async def get_product(
    product_id: str, actor: ActorDependency, control: ServiceDependency
) -> dict[str, Any]:
    return await control.get_product(actor, product_id)


@router.put("/products/{product_id}")
async def update_product(
    product_id: str,
    body: ProductUpdate,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.update_product(actor, product_id, body)


@router.post("/products/{product_id}:archive")
async def archive_product(
    product_id: str,
    body: ProductArchiveRequest,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.archive_product(actor, product_id, body)


@router.put("/products/{product_id}/media")
async def update_product_media(
    product_id: str,
    body: ProductMediaUpdate,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.update_product_media(actor, product_id, body)


@router.post("/products:batch-update-price")
async def batch_update_product_price(
    body: ProductBatchUpdatePrice,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.batch_update_product_price(actor, body)


@router.post("/products:batch-update-group")
async def batch_update_product_group(
    body: ProductBatchUpdateGroup,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.batch_update_product_group(actor, body)


@router.post("/products:batch-delete")
async def batch_delete_products(
    body: ProductBatchDelete,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.batch_delete_products(actor, body)


@router.post("/products:import", status_code=status.HTTP_201_CREATED)
async def import_products(
    body: ProductImportRequest,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.import_products(actor, body)


@router.post("/products:filter")
async def filter_products(
    body: ProductFilterRequest,
    actor: ActorDependency,
    control: ServiceDependency,
) -> list[dict[str, Any]]:
    return await control.filter_products(actor, body)


@router.put("/media/uploads/{upload_id}/content", status_code=status.HTTP_204_NO_CONTENT)
async def put_media_upload_content(
    upload_id: str,
    request: Request,
    control: ServiceDependency,
) -> Response:
    body = await request.body()
    content_type = request.headers.get("content-type") or "application/octet-stream"
    await control.store_media_upload_content(upload_id, body, content_type)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/media/uploads/{upload_id}:complete")
async def complete_media_upload(
    upload_id: str,
    body: MediaUploadComplete,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    del body
    return await control.complete_media_upload(actor, upload_id)


@router.post("/media/assets:register", status_code=status.HTTP_201_CREATED)
async def register_media_asset(
    body: MediaCreate, actor: ActorDependency, control: ServiceDependency
) -> dict[str, Any]:
    return await control.create_media(actor, body)


@router.post("/media/{source_asset_id}/derivatives", status_code=status.HTTP_202_ACCEPTED)
async def request_media_derivative(
    source_asset_id: str,
    body: MediaDerivativeCreate,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.request_media_derivative(actor, source_asset_id, body)


@router.post("/media/derivatives/{derivative_id}:result")
async def record_media_derivative_result(
    derivative_id: str,
    body: MediaDerivativeResult,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.record_media_derivative_result(actor, derivative_id, body)


@router.post("/content", status_code=status.HTTP_201_CREATED)
async def create_content(
    body: ContentCreate, actor: ActorDependency, control: ServiceDependency
) -> dict[str, Any]:
    return await control.create_content(actor, body)


@router.get("/content")
async def list_content(
    actor: ActorDependency,
    control: ServiceDependency,
    kind: Annotated[str | None, Query()] = None,
) -> list[dict[str, Any]]:
    items = await control.list_content(actor)
    if kind:
        return [item for item in items if item.get("kind") == kind]
    return items


@router.get("/content/{content_id}")
async def get_content(
    content_id: str, actor: ActorDependency, control: ServiceDependency
) -> dict[str, Any]:
    return await control.get_content(actor, content_id)


@router.post("/content/{content_id}/revisions", status_code=status.HTTP_201_CREATED)
async def create_revision(
    content_id: str,
    body: RevisionCreate,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.add_revision(actor, content_id, body)


@router.post("/content/{content_id}:archive")
async def archive_content(
    content_id: str,
    body: ContentArchiveRequest,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.archive_content(actor, content_id, body)


@router.post("/content/{content_id}:dispatch-xianyu", status_code=status.HTTP_201_CREATED)
async def dispatch_post_to_xianyu(
    content_id: str,
    body: ContentXianyuDispatchRequest,
    actor: ActorDependency,
    control: ServiceDependency,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    result = await control.dispatch_post_to_xianyu(actor, content_id, body, idempotency_key)
    if not result.get("created"):
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotency-Replayed"] = "true"
    return result


@router.post("/content-groups", status_code=status.HTTP_201_CREATED)
async def create_content_group(
    body: ContentGroupCreate,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.create_content_group(actor, body)


@router.get("/content-groups")
async def list_content_groups(
    actor: ActorDependency, control: ServiceDependency
) -> list[dict[str, Any]]:
    return await control.list_content_groups(actor)


@router.post("/content-groups/{group_id}/members", status_code=status.HTTP_201_CREATED)
async def add_content_group_member(
    group_id: str,
    body: ContentGroupMembershipCreate,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.add_content_group_member(actor, group_id, body)


@router.delete("/content-groups/{group_id}/members/{content_id}", status_code=204)
async def remove_content_group_member(
    group_id: str,
    content_id: str,
    actor: ActorDependency,
    control: ServiceDependency,
) -> Response:
    await control.remove_content_group_member(actor, group_id, content_id)
    return Response(status_code=204)


@router.post("/automation-packages", status_code=status.HTTP_201_CREATED)
async def register_automation_package(
    body: AutomationPackageCreate,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.register_automation(actor, body)


@router.post("/automation-packages/{version_id}:promote")
async def promote_automation_package(
    version_id: str,
    body: AutomationPromotionRequest,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.promote_automation(actor, version_id, body)


@router.post("/recipes", status_code=status.HTTP_201_CREATED)
async def register_recipe_package(
    actor: ActorDependency,
    control: ServiceDependency,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    return await control.register_recipe(actor, body)


@router.get("/recipes")
async def list_recipes(actor: ActorDependency, control: ServiceDependency) -> dict[str, Any]:
    return await control.list_recipes(actor)


@router.post("/recipes/{version_id}:rollback")
async def rollback_recipe(
    version_id: str,
    body: RecipeRollbackRequest,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.rollback_recipe(actor, version_id, body)


@router.get("/recipes/{version_id}")
async def get_recipe_package(
    version_id: str,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.get_recipe(actor, version_id)


@router.post("/recipes/{version_id}:publish")
async def publish_recipe_package(
    version_id: str,
    body: RecipePublishRequest,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.publish_recipe(actor, version_id, body)


@router.post("/recipes/{version_id}:revoke")
async def revoke_recipe_package(
    version_id: str,
    body: RecipePublishRequest,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.revoke_recipe(actor, version_id, body)


@router.post("/apk-artifacts", status_code=status.HTTP_201_CREATED)
async def register_apk_artifact(
    body: ApkArtifactCreate,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.register_apk(actor, body)


@router.post("/publish-plans")
async def create_publish_plan(
    body: PublishPlanCreate,
    actor: ActorDependency,
    control: ServiceDependency,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    result, created = await control.create_plan(actor, idempotency_key or "", body)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response.headers["Idempotency-Replayed"] = "false" if created else "true"
    return result


@router.post("/publish-plans/{plan_id}:submit")
async def submit_publish_plan(
    plan_id: str, actor: ActorDependency, control: ServiceDependency
) -> dict[str, Any]:
    return await control.submit_plan(actor, plan_id)


@router.post("/publish-plans/{plan_id}:approve")
async def approve_publish_plan(
    plan_id: str,
    body: ApprovalRequest,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.decide_approval(actor, plan_id, body)


@router.post("/publish-plans/{plan_id}:cancel")
async def cancel_publish_plan(
    plan_id: str, actor: ActorDependency, control: ServiceDependency
) -> dict[str, Any]:
    return await control.cancel_plan(actor, plan_id)


@router.get("/publish-plans/{plan_id}")
async def get_publish_plan(
    plan_id: str, actor: ActorDependency, control: ServiceDependency
) -> dict[str, Any]:
    return await control.get_plan(actor, plan_id)


@router.post("/publish-targets/{target_id}/commit-intents", status_code=status.HTTP_201_CREATED)
async def create_commit_intent(
    target_id: str,
    body: CommitIntentCreate,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.create_commit_intent(
        actor, target_id, body.fencing_token, body.before_commit_evidence_id
    )


@router.post("/publish-targets/{target_id}:state")
async def update_target_state(
    target_id: str,
    body: TargetStateUpdate,
    actor: ActorDependency,
    control: ServiceDependency,
) -> dict[str, Any]:
    return await control.update_target_state(
        actor, target_id, PublishState(body.state), body.detail
    )


@router.get("/audit-events")
async def list_audit_events(
    actor: ActorDependency,
    control: ServiceDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict[str, Any]]:
    return await control.audit_events(actor, limit)


@router.get("/events/poll")
async def poll_events(
    actor: ActorDependency,
    control: ServiceDependency,
    after_id: Annotated[str | None, Query(alias="afterId")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict[str, Any]]:
    return await control.events(actor, after_id, limit)


@router.get("/events")
async def stream_events(
    request: Request,
    actor: ActorDependency,
    control: ServiceDependency,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        cursor = last_event_id
        while not await request.is_disconnected():
            events = await control.events(actor, cursor, 100)
            if not events:
                yield ": heartbeat\n\n"
            for event in events:
                cursor = str(event["id"])
                data = json.dumps(jsonable_encoder(event), separators=(",", ":"))
                yield f"id: {cursor}\nevent: {event['type']}\ndata: {data}\n\n"
            await asyncio.sleep(request.app.state.settings.event_poll_seconds)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
