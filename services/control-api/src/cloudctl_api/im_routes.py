"""IM aggregation routes: companion push + operator inbox (pa-im/20260913.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from .auth import current_actor
from .im_service import ImService
from .mobile_routes import binding

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


class ImMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    peer_key: str = Field(alias="peerKey", min_length=1, max_length=128)
    peer_name: str = Field(alias="peerName", min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4000)
    occurred_at: datetime = Field(alias="occurredAt")


class ImBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    messages: list[ImMessageIn] = Field(min_length=1, max_length=20)


class ImReplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    text: str = Field(min_length=1, max_length=500)


@companion_router.post("/messages")
async def push_messages(body: ImBatchIn, binding_row: BindingDep, im: Service) -> dict[str, int]:
    return await im.ingest(
        binding_row,
        [
            {
                "peerKey": item.peer_key,
                "peerName": item.peer_name,
                "text": item.text,
                "occurredAt": item.occurred_at,
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
) -> dict[str, Any]:
    items = await im.list_threads(actor, device_id, unread, after, limit)
    return {"items": items, "count": len(items)}


@operator_router.get("/threads/{thread_id}/messages")
async def list_messages(
    thread_id: str,
    actor: ActorDep,
    im: Service,
    after: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
) -> dict[str, Any]:
    items = await im.list_messages(actor, thread_id, after, limit)
    return {"items": items, "count": len(items)}


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
async def get_im_config(actor: ActorDep, im: Service, device_id: str = Query(alias="deviceId")) -> dict[str, Any]:
    return await im.get_config(actor, device_id)


@operator_router.put("/config")
async def put_im_config(
    body: ImConfigIn, actor: ActorDep, im: Service, device_id: str = Query(alias="deviceId")
) -> dict[str, Any]:
    return await im.upsert_config(actor, device_id, {
        "enabled": body.enabled, "platforms": body.platforms, "mode": body.mode,
        "dutyStart": body.duty_start, "dutyEnd": body.duty_end,
    })


@companion_router.get("/config")
async def companion_im_config(binding_row: BindingDep, im: Service) -> dict[str, Any]:
    return await im.companion_config(binding_row)
