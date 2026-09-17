"""FastAPI composition root."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from cloudctl_domain import DomainError
from cloudctl_observability import bind_context, configure_logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from .apk_releases import companion_router as apk_release_companion_router
from .apk_releases import operator_router as apk_release_operator_router
from .auth import OidcJwtVerifier
from .db import Database
from .debug_routes import router as debug_router
from .debug_service import DebugSessionService
from .dev_seed import seed_development_data
from .features.schedules import FleetScheduleService
from .features.schedules.routes import router as fleet_schedule_router
from .fleet_orders import FleetOrdersService
from .fleet_orders import router as fleet_orders_router
from .im_routes import companion_router as im_companion_router
from .im_routes import operator_router as im_operator_router
from .im_service import ImService
from .live import LiveService
from .live import companion_router as live_companion_router
from .live import operator_router as live_operator_router
from .media_store import ObjectStore, create_object_store
from .mobile_routes import companion_router
from .mobile_routes import operator_router as mobile_operator_router
from .mobile_service import MobileTaskService
from .operation_routes import router as operation_router
from .operation_service import OperationService
from .orders_routes import companion_router as orders_companion_router
from .orders_routes import operator_router as orders_operator_router
from .orders_service import OrderService
from .platform_task_routes import router as platform_task_router
from .platform_tasks import PlatformTaskService
from .routes import router
from .schedule_routes import router as schedule_router
from .schedules import TaskScheduleService
from .services import ControlService
from .settings import Settings, get_settings
from .source_routes import router as source_router
from .wechat_client import WeChatTransport
from .wechat_routes import router as wechat_router
from .wechat_service import WeChatPublisherService
from .xianyu_maintenance import XianyuMaintenanceService
from .xianyu_maintenance_routes import router as xianyu_maintenance_router
from .xianyu_orders import XianyuOrdersService
from .xianyu_orders_routes import router as xianyu_orders_router
from .xianyu_publish import xianyu_publish_router


def _problem(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    retryable: bool = False,
    fields: dict[str, str] | None = None,
) -> JSONResponse:
    correlation_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=status,
        content={
            "type": f"urn:cloudctl:problem:{code.lower()}",
            "title": title,
            "status": status,
            "code": code,
            "detail": detail,
            "correlation_id": correlation_id,
            "retryable": retryable,
            "fields": fields or {},
        },
        media_type="application/problem+json",
    )


def create_app(
    settings: Settings | None = None,
    *,
    object_store: ObjectStore | None = None,
    wechat_transport: WeChatTransport | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    database = Database(resolved_settings)
    oidc_verifier = (
        None if resolved_settings.dev_auth_bypass else OidcJwtVerifier(resolved_settings)
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        if resolved_settings.auto_create_schema():
            await database.create_schema()
        if resolved_settings.auto_seed_development_data():
            await seed_development_data(database)
        try:
            yield
        finally:
            if oidc_verifier is not None:
                await oidc_verifier.close()
            await app.state.wechat_publisher_service.close_transport()
            await database.dispose()

    app = FastAPI(
        title="CloudCtl Control API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database = database
    app.state.oidc_verifier = oidc_verifier
    resolved_object_store = (
        object_store if object_store is not None else create_object_store(resolved_settings)
    )
    app.state.object_store = resolved_object_store
    app.state.mobile_task_service = MobileTaskService(database, resolved_object_store)
    app.state.xianyu_maintenance_service = XianyuMaintenanceService(
        database, app.state.mobile_task_service
    )
    app.state.orders_service = OrderService(database)
    app.state.fleet_orders_service = FleetOrdersService(database)
    app.state.xianyu_orders_service = XianyuOrdersService(
        database, app.state.mobile_task_service
    )
    app.state.platform_task_service = PlatformTaskService(database, app.state.mobile_task_service)
    app.state.task_schedule_service = TaskScheduleService(database, app.state.platform_task_service)
    fleet_platform = app.state.platform_task_service
    app.state.fleet_schedule_service = FleetScheduleService(database, fleet_platform)
    app.state.control_service = ControlService(
        database,
        resolved_settings,
        resolved_object_store,
        mobile_task_service=app.state.mobile_task_service,
    )
    app.state.operation_service = OperationService(
        database, resolved_settings, app.state.mobile_task_service
    )
    app.state.debug_session_service = DebugSessionService(database, resolved_settings)
    app.state.wechat_publisher_service = WeChatPublisherService(
        database, resolved_settings, transport=wechat_transport
    )
    app.state.im_service = ImService(app.state.mobile_task_service)
    app.state.live_service = LiveService(app.state.mobile_task_service)
    app.state.mobile_task_service.live_service = app.state.live_service
    app.dependency_overrides[get_settings] = lambda: resolved_settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Authorization",
            "Content-Type",
            "X-Checksum-SHA256",
            "X-Amz-Checksum-Sha256",
            "Idempotency-Key",
            "Last-Event-ID",
            "X-Debug-Relay-Token",
            "X-Request-Id",
        ]
        + (
            ["X-MFA", "X-Roles", "X-Tenant-Id", "X-User-Id"]
            if resolved_settings.dev_auth_bypass
            else []
        ),
        expose_headers=["Idempotency-Replayed", "X-Request-Id", "ETag"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        with bind_context(request_id=request_id):
            response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return _problem(
            request,
            status=exc.status,
            code=exc.code,
            title=exc.__class__.__name__,
            detail=exc.detail,
            retryable=exc.retryable,
            fields=exc.fields,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        def field_name(loc: tuple[int | str, ...]) -> str:
            parts = [str(part) for part in loc]
            if parts and parts[0] == "body":
                parts = parts[1:]
            return ".".join(parts) or "body"

        fields = {
            field_name(error["loc"]): error["msg"] for error in exc.errors()
        }
        return _problem(
            request,
            status=422,
            code="VALIDATION_ERROR",
            title="Request validation failed",
            detail="one or more request fields are invalid",
            fields=fields,
        )

    @app.get("/health/live", include_in_schema=False)
    async def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    async def health_ready() -> dict[str, str]:
        await database.ping()
        return {"status": "ok", "repositoryMode": resolved_settings.repository_mode}

    @app.get("/healthz", include_in_schema=False)
    async def health_compatibility() -> dict[str, str]:
        return {"status": "ok", "repositoryMode": resolved_settings.repository_mode}

    app.include_router(router)
    app.include_router(operation_router)
    app.include_router(source_router)
    app.include_router(wechat_router)
    app.include_router(xianyu_maintenance_router)
    app.include_router(xianyu_publish_router)
    app.include_router(xianyu_orders_router)
    app.include_router(orders_operator_router)
    app.include_router(orders_companion_router)
    app.include_router(fleet_orders_router)
    app.include_router(debug_router)
    app.include_router(mobile_operator_router)
    app.include_router(platform_task_router)
    app.include_router(schedule_router)
    app.include_router(fleet_schedule_router)
    app.include_router(im_operator_router)
    app.include_router(im_companion_router)
    app.include_router(live_operator_router)
    app.include_router(live_companion_router)
    app.include_router(companion_router)
    app.include_router(apk_release_operator_router)
    app.include_router(apk_release_companion_router)
    return app


app = create_app()
