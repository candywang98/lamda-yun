"""Versioned HTTP routes for debug-session lifecycle and evidence."""

from __future__ import annotations

from typing import Annotated, Any, cast

from cloudctl_domain import Actor
from fastapi import APIRouter, Depends, Header, Request, Response, status

from .auth import current_actor
from .debug_schemas import (
    DebugEvidenceCreate,
    DebugEvidenceView,
    DebugHeartbeat,
    DebugSessionCreate,
    DebugSessionCreateResult,
    DebugSessionDetailView,
    DebugSessionExchange,
    DebugSessionExchangeResult,
    DebugSessionRevoke,
    DebugSessionView,
)
from .debug_service import DebugSessionService

router = APIRouter(prefix="/api/v1/debug-sessions", tags=["debug-sessions"])
ActorDependency = Annotated[Actor, Depends(current_actor)]


def service(request: Request) -> DebugSessionService:
    return cast(DebugSessionService, request.app.state.debug_session_service)


ServiceDependency = Annotated[DebugSessionService, Depends(service)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=DebugSessionCreateResult,
)
async def create_debug_session(
    body: DebugSessionCreate,
    actor: ActorDependency,
    debug: ServiceDependency,
) -> dict[str, Any]:
    return await debug.create(actor, body)


@router.post(":exchange", response_model=DebugSessionExchangeResult)
async def exchange_debug_launch_code(
    body: DebugSessionExchange,
    actor: ActorDependency,
    debug: ServiceDependency,
) -> dict[str, Any]:
    return await debug.exchange(actor, body.launch_code)


@router.get("/{session_id}", response_model=DebugSessionDetailView)
async def get_debug_session(
    session_id: str,
    actor: ActorDependency,
    debug: ServiceDependency,
) -> dict[str, Any]:
    return await debug.get(actor, session_id)


@router.post("/{session_id}:heartbeat", response_model=DebugSessionView)
async def heartbeat_debug_session(
    session_id: str,
    body: DebugHeartbeat,
    actor: ActorDependency,
    debug: ServiceDependency,
    relay_token: Annotated[str, Header(alias="X-Debug-Relay-Token", min_length=20)],
) -> dict[str, Any]:
    return await debug.heartbeat(actor, session_id, relay_token, body)


@router.post("/{session_id}:revoke", response_model=DebugSessionView)
async def revoke_debug_session(
    session_id: str,
    body: DebugSessionRevoke,
    actor: ActorDependency,
    debug: ServiceDependency,
) -> dict[str, Any]:
    return await debug.revoke(actor, session_id, body.reason)


@router.post("/{session_id}/evidence", response_model=DebugEvidenceView)
async def register_debug_evidence(
    session_id: str,
    body: DebugEvidenceCreate,
    actor: ActorDependency,
    debug: ServiceDependency,
    response: Response,
    relay_token: Annotated[str, Header(alias="X-Debug-Relay-Token", min_length=20)],
) -> dict[str, Any]:
    result, created = await debug.add_evidence(actor, session_id, relay_token, body)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return result
