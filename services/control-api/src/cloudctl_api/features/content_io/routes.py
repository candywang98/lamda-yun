"""F11 content-io routes: import dry-run/apply, CSV export, revision history."""

from __future__ import annotations

from typing import Annotated, Any, cast

from cloudctl_domain import Actor
from fastapi import APIRouter, Depends, Query, Request, Response

from ...auth import current_actor
from .schemas import ContentImportRunRequest
from .service import ContentIOService

router = APIRouter(prefix="/api/v1/content-io", tags=["content-io"])
ActorDep = Annotated[Actor, Depends(current_actor)]


def service(request: Request) -> ContentIOService:
    return cast(ContentIOService, request.app.state.content_io_service)


Service = Annotated[ContentIOService, Depends(service)]


@router.post("/products:import")
async def run_import(
    body: ContentImportRunRequest, actor: ActorDep, content_io: Service
) -> dict[str, Any]:
    return await content_io.run_import(actor, body)


@router.get("/products:export")
async def export_products(
    actor: ActorDep,
    content_io: Service,
    status_filter: Annotated[
        str | None,
        Query(alias="status", pattern="^(ACTIVE|ARCHIVED)$"),
    ] = None,
    category: Annotated[str | None, Query(max_length=160)] = None,
) -> Response:
    filename, csv_text = await content_io.export_csv(
        actor, status_filter=status_filter, category=category
    )
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/products/{product_id}/revisions")
async def product_revisions(
    product_id: str,
    actor: ActorDep,
    content_io: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return await content_io.revisions(actor, product_id, limit=limit, offset=offset)
