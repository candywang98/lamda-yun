"""F10 media-assets feature routes."""

from __future__ import annotations

from typing import Annotated, Any, cast

from cloudctl_domain import Actor
from fastapi import APIRouter, Depends, Request

from ...auth import current_actor
from .schemas import MediaPoolFreezeRequest, PublishPreflightRequest, WatermarkRenderRequest
from .service import MediaAssetsService

router = APIRouter(prefix="/api/v1/media-assets", tags=["media-assets"])
ActorDep = Annotated[Actor, Depends(current_actor)]


def service(request: Request) -> MediaAssetsService:
    return cast(MediaAssetsService, request.app.state.media_assets_service)


Service = Annotated[MediaAssetsService, Depends(service)]


@router.post("/{source_asset_id}/watermark:render")
async def render_watermark(
    source_asset_id: str,
    body: WatermarkRenderRequest,
    actor: ActorDep,
    media_assets: Service,
) -> dict[str, Any]:
    return await media_assets.render_watermark(actor, source_asset_id, body)


@router.post("/pools:freeze")
async def freeze_pool(
    body: MediaPoolFreezeRequest,
    actor: ActorDep,
    media_assets: Service,
) -> dict[str, Any]:
    return await media_assets.freeze_pool(actor, body)


@router.post("/publish:preflight")
async def publish_preflight(
    body: PublishPreflightRequest,
    actor: ActorDep,
    media_assets: Service,
) -> dict[str, Any]:
    return await media_assets.preflight(actor, body)
