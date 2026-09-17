from __future__ import annotations

import uuid
from typing import Annotated, Any, cast

from cloudctl_domain import Actor, AuthenticationError
from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import JSONResponse

from .auth import current_actor
from .db import MobileBindingRow
from .fleet_identity import CursorTooOldError
from .mobile_actions import IntentRequest, MobileActionService, OutcomeRequest
from .mobile_schemas import (
    DevicePreviewSessionCreate,
    DevicePreviewUpload,
    MobileClaimRequest,
    MobileDeviceCreate,
    MobileEnrollmentCreate,
    MobileEnrollRequest,
    MobileHeartbeat,
    MobileMediaManifestRequest,
    MobilePublishListingRequest,
    MobileTaskCompletion,
    MobileTaskCreate,
    MobileTaskEvent,
    MobileTaskFailure,
    MobileTaskRelease,
)
from .mobile_service import (
    CompanionControlAckRequest,
    MobileDeviceHeartbeatV2,
    MobileTaskService,
)

operator_router = APIRouter(prefix="/api/v1/mobile", tags=["mobile-tasks"])
companion_router = APIRouter(prefix="/companion/v2", tags=["mobile-companion"])


def service(request: Request) -> MobileTaskService:
    return cast(MobileTaskService, request.app.state.mobile_task_service)


Service = Annotated[MobileTaskService, Depends(service)]
ActorDep = Annotated[Actor, Depends(current_actor)]


async def binding(request: Request, mobile: Service) -> MobileBindingRow:
    scheme, separator, token = request.headers.get("Authorization", "").partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token:
        raise AuthenticationError("Companion bearer authentication is required")
    return await mobile.authenticate(token)


Binding = Annotated[MobileBindingRow, Depends(binding)]


@operator_router.post("/enrollments", status_code=status.HTTP_201_CREATED)
async def create_enrollment(
    body: MobileEnrollmentCreate, actor: ActorDep, mobile: Service
) -> dict[str, Any]:
    return await mobile.create_enrollment(actor, body.device_id, body.ttl_seconds)


@operator_router.post("/devices", status_code=status.HTTP_201_CREATED)
async def create_direct_device(
    body: MobileDeviceCreate, actor: ActorDep, mobile: Service
) -> dict[str, Any]:
    return await mobile.create_direct_device(
        actor,
        body.logical_name,
        body.android_version,
        body.companion_version,
        body.labels,
    )


@operator_router.post("/tasks")
async def create_task(
    body: MobileTaskCreate,
    actor: ActorDep,
    mobile: Service,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    result, created = await mobile.create_task(actor, idempotency_key or "", body)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response.headers["Idempotency-Replayed"] = "false" if created else "true"
    return result


@operator_router.get("/tasks")
async def list_tasks(actor: ActorDep, mobile: Service) -> list[dict[str, Any]]:
    return await mobile.list_tasks(actor)


@operator_router.get("/tasks/{task_id}")
async def get_task(task_id: str, actor: ActorDep, mobile: Service) -> dict[str, Any]:
    return await mobile.get_task(actor, task_id)


@operator_router.post("/devices/{device_id}/preview/sessions", status_code=status.HTTP_201_CREATED)
async def start_device_preview(
    device_id: str, body: DevicePreviewSessionCreate, actor: ActorDep, mobile: Service
) -> dict[str, Any]:
    return await mobile.start_preview(
        actor,
        device_id,
        ttl_seconds=body.ttl_seconds,
        capture_interval_ms=body.capture_interval_ms,
    )


@operator_router.get("/devices/{device_id}/preview")
async def get_device_preview(device_id: str, actor: ActorDep, mobile: Service) -> dict[str, Any]:
    return await mobile.preview_status(actor, device_id)


@operator_router.get("/devices/{device_id}/preview/frame")
async def get_device_preview_frame(
    device_id: str,
    actor: ActorDep,
    mobile: Service,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    frame = await mobile.preview_frame(actor, device_id)
    if frame is None:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    image, content_type, digest = frame
    etag = f'"{digest}"'
    if if_none_match and if_none_match.strip() == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    return Response(
        content=image,
        media_type=content_type,
        headers={"Cache-Control": "no-store", "ETag": etag},
    )


@operator_router.post("/devices/{device_id}/preview/sessions/{session_id}:stop")
async def stop_device_preview(
    device_id: str, session_id: str, actor: ActorDep, mobile: Service
) -> dict[str, Any]:
    return await mobile.stop_preview(actor, device_id, session_id)


@companion_router.post("/enroll", status_code=status.HTTP_201_CREATED)
async def enroll(body: MobileEnrollRequest, mobile: Service) -> dict[str, Any]:
    return await mobile.enroll(body.code, body.app_instance_id, body.companion_version)


@companion_router.post("/devices/heartbeat")
async def device_heartbeat(
    body: MobileDeviceHeartbeatV2, current: Binding, mobile: Service
) -> dict[str, Any]:
    return await mobile.device_heartbeat(current, body)


@companion_router.get("/control")
async def control_pull(
    after: int,
    current: Binding,
    mobile: Service,
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
) -> Any:
    # control-plane/v1 §2.1: 410 CURSOR_TOO_OLD carries snapshotRequired so
    # the client converges through the snapshot channel instead of treating
    # the compacted window as "no changes".
    try:
        return await mobile.control_pull(current, after, limit)
    except CursorTooOldError as exc:
        return JSONResponse(
            status_code=410,
            content={
                "code": "CURSOR_TOO_OLD",
                "snapshotRequired": True,
                "detail": exc.detail,
            },
            media_type="application/problem+json",
        )


@companion_router.get("/reconcile-snapshot")
async def reconcile_snapshot(current: Binding, mobile: Service) -> dict[str, Any]:
    return await mobile.reconcile_snapshot(current)


@companion_router.post("/control/ack")
async def control_ack(
    body: CompanionControlAckRequest, current: Binding, mobile: Service
) -> dict[str, Any]:
    return await mobile.control_ack(current, body)


@companion_router.get("/accounts/status")
async def account_status(current: Binding, mobile: Service) -> list[dict[str, Any]]:
    return await mobile.account_status(current)


@companion_router.post("/devices/preview")
async def upload_device_preview(
    body: DevicePreviewUpload, current: Binding, mobile: Service
) -> dict[str, Any]:
    return await mobile.upload_preview(current, body)


@companion_router.post("/tasks/publish-listing")
async def publish_listing(
    body: MobilePublishListingRequest,
    current: Binding,
    mobile: Service,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    result, created = await mobile.enqueue_bound_text_publish(
        current,
        description=body.description,
        price=body.price,
        media_asset_ids=body.media_asset_ids,
        delivery_id=body.delivery_id,
        auto_publish=body.auto_publish,
        key=idempotency_key or f"companion-publish:{current.device_id}:{uuid.uuid4()}",
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response.headers["Idempotency-Replayed"] = "false" if created else "true"
    return result


@companion_router.post("/tasks/claim")
async def claim(
    body: MobileClaimRequest, current: Binding, mobile: Service, response: Response
) -> dict[str, Any] | None:
    result = await mobile.claim(current, body.lease_seconds)
    if result is None:
        response.status_code = status.HTTP_204_NO_CONTENT
    return result


@companion_router.post("/media/manifest")
async def media_manifest(
    body: MobileMediaManifestRequest, current: Binding, mobile: Service
) -> dict[str, Any]:
    return await mobile.media_manifest(current, body.delivery_id, body.asset_ids)


@companion_router.get("/media/{asset_id}")
async def download_media(asset_id: str, current: Binding, mobile: Service) -> Response:
    content, content_type, digest = await mobile.download_media(current, asset_id)
    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "no-store", "X-Content-SHA256": digest},
    )


@companion_router.get("/recipes/active")
async def list_active_recipes(current: Binding, mobile: Service) -> dict[str, Any]:
    return await mobile.list_active_recipes(current)


@companion_router.get("/recipes/{version_id}")
async def download_recipe(version_id: str, current: Binding, mobile: Service) -> Response:
    content, digest = await mobile.download_recipe(current, version_id)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Cache-Control": "no-store", "X-Content-SHA256": digest},
    )


@companion_router.post("/tasks/{task_id}/heartbeat")
async def heartbeat(
    task_id: str, body: MobileHeartbeat, current: Binding, mobile: Service
) -> dict[str, Any]:
    return await mobile.heartbeat(
        current, task_id, body.lease_id, body.current_step, body.lease_seconds
    )


@companion_router.post("/tasks/{task_id}/release")
async def release(
    task_id: str, body: MobileTaskRelease, current: Binding, mobile: Service
) -> dict[str, Any]:
    return await mobile.release(current, task_id, body.lease_id, body.reason)


@companion_router.post("/tasks/{task_id}/events")
async def event(
    task_id: str, body: MobileTaskEvent, current: Binding, mobile: Service, response: Response
) -> dict[str, Any]:
    result, created = await mobile.event(
        current,
        task_id,
        body.lease_id,
        body.sequence,
        body.event_type,
        body.step_index,
        body.payload,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response.headers["Idempotency-Replayed"] = "false" if created else "true"
    return result


@companion_router.post("/tasks/{task_id}/complete")
async def complete(
    task_id: str, body: MobileTaskCompletion, current: Binding, mobile: Service
) -> dict[str, Any]:
    result = dict(body.result)
    if body.result_type:
        result["resultType"] = body.result_type
    if body.schema_version is not None:
        result["schemaVersion"] = body.schema_version
    return await mobile.finish(
        current, task_id, body.lease_id, status="SUCCEEDED", result=result
    )


@companion_router.post("/tasks/{task_id}/fail")
async def fail(
    task_id: str, body: MobileTaskFailure, current: Binding, mobile: Service
) -> dict[str, Any]:
    return await mobile.finish(
        current,
        task_id,
        body.lease_id,
        status="FAILED",
        result={},
        error_code=body.error_code,
        detail=body.detail,
    )


@companion_router.delete("/binding", status_code=status.HTTP_204_NO_CONTENT)
async def unbind(current: Binding, mobile: Service) -> Response:
    await mobile.unbind(current)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def actions(request: Request, mobile: Service) -> MobileActionService:
    return MobileActionService(mobile, request.app.state.settings.automation_signing_public_keys)


Actions = Annotated[MobileActionService, Depends(actions)]


@companion_router.post("/tasks/{task_id}/actions/intent")
async def action_intent(
    task_id: str, body: IntentRequest, current: Binding, ledger: Actions, response: Response
) -> dict[str, Any]:
    result, created = await ledger.intent(current, task_id, body)
    response.status_code = 201 if created else 200
    return result


@companion_router.post("/tasks/{task_id}/actions/{action_key}/outcome")
async def action_outcome(
    task_id: str, action_key: str, body: OutcomeRequest, current: Binding, ledger: Actions
) -> dict[str, Any]:
    return await ledger.outcome(current, task_id, action_key, body)


@companion_router.get("/tasks/{task_id}/actions/{action_key}")
async def get_action(
    task_id: str, action_key: str, current: Binding, ledger: Actions
) -> dict[str, Any]:
    return await ledger.get(current, task_id, action_key)
