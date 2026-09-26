"""WeChat Official Account publisher routes (V1-26 starter slice).

Publishing is gated by the server-side controlled-commit ledger:
``authorize-publish`` (publish.approve) freezes the intent, ``:submit``
(publish.create) consumes the single submit attempt, ``:poll`` reconciles
with freepublish/get. See ``wechat_service`` for the semantics.
"""

from __future__ import annotations

from typing import Annotated, Any, cast

from cloudctl_domain import Actor
from fastapi import APIRouter, Depends, Header, Request, Response, status

from .auth import current_actor
from .wechat_schemas import (
    WechatAccountCreate,
    WechatDraftCreate,
    WechatPublishAuthorize,
)
from .wechat_service import WeChatPublisherService

router = APIRouter(prefix="/api/v1/wechat", tags=["wechat-publisher"])
ActorDep = Annotated[Actor, Depends(current_actor)]


def service(request: Request) -> WeChatPublisherService:
    return cast(WeChatPublisherService, request.app.state.wechat_publisher_service)


Service = Annotated[WeChatPublisherService, Depends(service)]


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
async def register_account(
    body: WechatAccountCreate, actor: ActorDep, wechat: Service
) -> dict[str, Any]:
    return await wechat.register_account(actor, body)


@router.get("/accounts")
async def list_accounts(actor: ActorDep, wechat: Service) -> dict[str, Any]:
    items = await wechat.list_accounts(actor)
    return {"items": items, "count": len(items)}


@router.get("/accounts/{account_id}")
async def get_account(account_id: str, actor: ActorDep, wechat: Service) -> dict[str, Any]:
    return await wechat.get_account(actor, account_id)


@router.post("/drafts")
async def create_draft(
    body: WechatDraftCreate,
    actor: ActorDep,
    wechat: Service,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    draft, created = await wechat.create_draft(actor, idempotency_key or "", body)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response.headers["Idempotency-Replayed"] = "false" if created else "true"
    return draft


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str, actor: ActorDep, wechat: Service) -> dict[str, Any]:
    return await wechat.get_draft(actor, draft_id)


@router.post("/drafts/{draft_id}:authorize-publish")
async def authorize_publish(
    draft_id: str,
    body: WechatPublishAuthorize,
    actor: ActorDep,
    wechat: Service,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    publish, created = await wechat.authorize_publish(actor, draft_id, idempotency_key or "", body)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response.headers["Idempotency-Replayed"] = "false" if created else "true"
    return publish


@router.post("/publishes/{publish_id}:submit")
async def submit_publish(publish_id: str, actor: ActorDep, wechat: Service) -> dict[str, Any]:
    return await wechat.submit(actor, publish_id)


@router.post("/publishes/{publish_id}:poll")
async def poll_publish(publish_id: str, actor: ActorDep, wechat: Service) -> dict[str, Any]:
    return await wechat.poll(actor, publish_id)


@router.get("/publishes/{publish_id}")
async def get_publish(publish_id: str, actor: ActorDep, wechat: Service) -> dict[str, Any]:
    return await wechat.get_publish(actor, publish_id)
