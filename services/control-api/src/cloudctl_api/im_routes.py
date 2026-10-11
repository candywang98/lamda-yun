"""IM aggregation routes: companion push + operator inbox (pa-im/20260913.1)."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field

from .auth import current_actor
from .im_classifier import Category
from .im_service import ImService
from .mobile_routes import binding
from .mobile_schemas import ImChatCompletion

companion_router = APIRouter(prefix="/companion/v2/im", tags=["im-companion"])
operator_router = APIRouter(prefix="/api/v1/im", tags=["im-operator"])

BindingDep = Annotated[Any, Depends(binding)]
ActorDep = Annotated[Any, Depends(current_actor)]


def service(request: Request) -> ImService:
    return cast_service(request.app.state.im_service)


def cast_service(value: object) -> ImService:
    assert isinstance(value, ImService)
    return value


Service = Annotated[ImService, Depends(service)]
Bucket = Literal["all", "user", "notice", "review"]


class NotificationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    package_name: Literal["com.taobao.idlefish"] | None = Field(default=None, alias="packageName")
    channel_id: str | None = Field(default=None, alias="channelId", max_length=256)
    category: str | None = Field(default=None, max_length=64)


class ImMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    platform: Literal["xianyu"] | None = None
    peer_key: str = Field(alias="peerKey", min_length=1, max_length=128)
    peer_name: str = Field(alias="peerName", min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4000)
    occurred_at: datetime = Field(alias="occurredAt")
    notification_metadata: NotificationMetadata | None = Field(
        default=None, alias="notificationMetadata"
    )


class ImBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    messages: list[ImMessageIn] = Field(min_length=1, max_length=20)


class ImReplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    text: str = Field(min_length=1, max_length=500)


@companion_router.post("/messages")
async def push_messages(body: ImBatchIn, binding_row: BindingDep, im: Service) -> dict[str, int]:
    for item in body.messages:
        if item.platform is None and (
            "platform" in item.model_fields_set
            or binding_row.device_id not in im.legacy_xianyu_device_ids
        ):
            raise HTTPException(status_code=422, detail="platform is required")
    return await im.ingest(
        binding_row,
        [
            {
                "platform": item.platform or "xianyu",
                "peerKey": item.peer_key,
                "peerName": item.peer_name,
                "text": item.text,
                "occurredAt": item.occurred_at,
                "notificationMetadata": (
                    item.notification_metadata.model_dump(by_alias=True, exclude_none=True)
                    if item.notification_metadata is not None
                    else None
                ),
            }
            for item in body.messages
        ],
    )


@operator_router.get("/threads")
async def list_threads(
    actor: ActorDep,
    im: Service,
    device_id: str | None = Query(default=None, alias="deviceId"),
    unread: bool = Query(default=False),
    after: str | None = None,
    limit: int = Query(default=50, ge=1, le=50),
    bucket: Bucket = "all",
) -> dict[str, Any]:
    items = await im.list_threads(actor, device_id, unread, after, limit, bucket=bucket)
    counts = await im.bucket_counts(actor, device_id, unread)
    return {"items": items, "count": len(items), "bucketCounts": counts}


@operator_router.get("/threads/{thread_id}/messages")
async def list_messages(
    thread_id: str,
    actor: ActorDep,
    im: Service,
    after: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    latest: bool = Query(default=False),
    bucket: Bucket = "all",
) -> dict[str, Any]:
    items = await im.list_messages(actor, thread_id, after, limit, latest=latest, bucket=bucket)
    return {"items": items, "count": len(items)}


class ClassificationIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    category: Category | None
    expected_version: int = Field(alias="expectedVersion", ge=0, strict=True)


class ReclassificationIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    expected_version: int = Field(alias="expectedVersion", ge=0, strict=True)


@operator_router.post("/messages/{message_id}:classify")
async def classify_message(
    message_id: str,
    body: ClassificationIn,
    actor: ActorDep,
    im: Service,
) -> dict[str, Any]:
    return await im.correct_classification(actor, message_id, body.expected_version, body.category)


@operator_router.post("/messages/{message_id}:reclassify")
async def reclassify_message(
    message_id: str,
    body: ReclassificationIn,
    actor: ActorDep,
    im: Service,
) -> dict[str, Any]:
    return await im.reclassify(actor, message_id, body.expected_version)


@operator_router.post("/threads/{thread_id}:mark-read", status_code=status.HTTP_200_OK)
async def mark_read(thread_id: str, actor: ActorDep, im: Service) -> dict[str, Any]:
    return await im.mark_read(actor, thread_id)


@operator_router.post("/threads/{thread_id}:reply", status_code=status.HTTP_201_CREATED)
async def reply(thread_id: str, body: ImReplyIn, actor: ActorDep, im: Service) -> dict[str, Any]:
    return await im.reply(actor, thread_id, body.text)


class ImConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    enabled: bool = True
    platforms: list[str] = Field(min_length=1, max_length=4)
    mode: str = Field(default="NOTIFICATION", pattern="^(NOTIFICATION|DUTY)$")
    duty_start: str = Field(default="09:00", alias="dutyStart", pattern=r"^[0-2][0-9]:[0-5][0-9]$")
    duty_end: str = Field(default="23:00", alias="dutyEnd", pattern=r"^[0-2][0-9]:[0-5][0-9]$")


@operator_router.get("/config")
async def get_im_config(
    actor: ActorDep, im: Service, device_id: str = Query(alias="deviceId")
) -> dict[str, Any]:
    return await im.get_config(actor, device_id)


@operator_router.put("/config")
async def put_im_config(
    body: ImConfigIn, actor: ActorDep, im: Service, device_id: str = Query(alias="deviceId")
) -> dict[str, Any]:
    return await im.upsert_config(
        actor,
        device_id,
        {
            "enabled": body.enabled,
            "platforms": body.platforms,
            "mode": body.mode,
            "dutyStart": body.duty_start,
            "dutyEnd": body.duty_end,
        },
    )


@companion_router.get("/config")
async def companion_im_config(binding_row: BindingDep, im: Service) -> dict[str, Any]:
    return await im.companion_config(binding_row)


class ImChatCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")


@operator_router.post("/threads/{thread_id}:collect-body")
async def collect_body(
    thread_id: str,
    body: ImChatCreateIn,
    actor: ActorDep,
    im: Service,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> dict[str, Any]:
    from .im_chat_collection import create

    result, created = await create(im, actor, thread_id, idempotency_key)
    response.status_code = 201 if created else 200
    return result


@operator_router.get("/threads/{thread_id}/body-collections")
async def body_collections(thread_id: str, actor: ActorDep, im: Service) -> dict[str, Any]:
    from .im_chat_collection import list_collections

    return await list_collections(im, actor, thread_id)


async def complete_body_collection(
    task_id: str,
    body: ImChatCompletion,
    binding_row: BindingDep,
    im: Service,
) -> dict[str, Any]:
    from .im_chat_collection import complete

    return await complete(im, binding_row, task_id, body)


class ImChatCompletionRoute(APIRoute):
    """Bound raw input before FastAPI JSON parsing, including chunked bodies."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def bounded(request: Request) -> Response:
            chunks: list[bytes] = []
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 400000:
                    raise HTTPException(status_code=413, detail="IM collection upload too large")
                chunks.append(chunk)
            request._body = b"".join(chunks)
            return await handler(request)

        return bounded


companion_router.add_api_route(
    "/chat-collections/{task_id}:complete",
    complete_body_collection,
    methods=["POST"],
    route_class_override=ImChatCompletionRoute,
)
