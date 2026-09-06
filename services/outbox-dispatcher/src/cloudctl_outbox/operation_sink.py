"""Restricted Operations consumer backed by explicit local or HTTP executors."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
from cloudctl_api.db import (
    AutomationVersionRow,
    ContentRevisionRow,
    Database,
    OperationItemRow,
    OperationTaskRow,
    PublishPlanRow,
    PublishSnapshotRow,
)
from cloudctl_api.operation_runtime import OperationExecutorRegistry
from cloudctl_api.operation_schemas import OperationItemResultUpdate
from cloudctl_api.operation_service import (
    TERMINAL_ITEM_STATES,
    TERMINAL_TASK_STATES,
    OperationService,
)
from cloudctl_api.repository import ControlRepository
from cloudctl_api.settings import Settings
from cloudctl_domain import Actor, Role, canonical_hash
from sqlalchemy import select

from .sinks import EventEnvelope

EXECUTION_EVENT_TYPES = frozenset({"operation.task.created", "operation.task.approved"})
MAX_ADAPTER_RESPONSE_BYTES = 64 * 1024
SERVICE_USER_ID = uuid.uuid5(uuid.NAMESPACE_URL, "cloudctl:operation-executor")
PROHIBITED_CONTENT_FIELDS = frozenset(
    {
        "adb",
        "captcha",
        "command",
        "credential",
        "frida",
        "mitm",
        "password",
        "pem",
        "privatekey",
        "proxy",
        "script",
        "secret",
        "shell",
        "token",
    }
)


class OperationExecutorUnavailable(RuntimeError):
    pass


class OperationAdapterError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OperationExecutionRequest:
    event_id: str
    tenant_id: str
    task_id: str
    item_id: str
    operation_key: str
    resource_id: str
    parameters: dict[str, Any]
    context: dict[str, Any]

    @property
    def idempotency_key(self) -> str:
        return f"{self.task_id}:{self.item_id}"


class OperationHandler(Protocol):
    async def execute(self, request: OperationExecutionRequest) -> OperationItemResultUpdate: ...


class HttpOperationHandler:
    """Calls one deployment-configured endpoint with a fixed JSON contract."""

    def __init__(
        self,
        endpoint: str,
        bearer_token: str,
        client: httpx.AsyncClient,
    ) -> None:
        self.endpoint = endpoint
        self.bearer_token = bearer_token
        self.client = client

    async def execute(self, request: OperationExecutionRequest) -> OperationItemResultUpdate:
        response = await self.client.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "Idempotency-Key": request.idempotency_key,
                "X-Request-Id": request.event_id,
            },
            json={
                "taskId": request.task_id,
                "itemId": request.item_id,
                "tenantId": request.tenant_id,
                "operationKey": request.operation_key,
                "resourceId": request.resource_id,
                "parameters": request.parameters,
                "context": request.context,
            },
        )
        if response.status_code != 200:
            raise OperationAdapterError(
                f"operation adapter returned unexpected HTTP {response.status_code}"
            )
        if len(response.content) > MAX_ADAPTER_RESPONSE_BYTES:
            raise OperationAdapterError("operation adapter response exceeds 64 KiB")
        try:
            return OperationItemResultUpdate.model_validate_json(response.content)
        except ValueError as exc:
            raise OperationAdapterError(
                "operation adapter returned an invalid result contract"
            ) from exc


class RevisionValidationHandler:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def execute(self, request: OperationExecutionRequest) -> OperationItemResultUpdate:
        policy_version = request.parameters.get("policyVersion", "baseline-v1")
        if policy_version != "baseline-v1":
            return OperationItemResultUpdate(
                status="BLOCKED",
                errorCode="POLICY_VERSION_UNAVAILABLE",
                detail="only the deployed baseline-v1 content policy can be evaluated",
            )
        async with self.database.unit_of_work() as session:
            revision = await session.scalar(
                select(ContentRevisionRow).where(
                    ContentRevisionRow.id == request.resource_id,
                    ContentRevisionRow.tenant_id == request.tenant_id,
                )
            )
            if revision is None:
                return OperationItemResultUpdate(
                    status="FAILED",
                    errorCode="REVISION_NOT_FOUND",
                    detail="content revision does not exist in the operation tenant",
                )
            if canonical_hash(revision.payload) != revision.payload_sha256:
                return OperationItemResultUpdate(
                    status="FAILED",
                    errorCode="REVISION_INTEGRITY_MISMATCH",
                    detail="stored revision payload does not match its immutable digest",
                )
            prohibited = _first_prohibited_field(revision.payload)
            if prohibited is not None:
                return OperationItemResultUpdate(
                    status="BLOCKED",
                    errorCode="CONTENT_POLICY_BLOCKED",
                    detail=f"baseline content policy rejected field: {prohibited}",
                )
        return OperationItemResultUpdate(
            status="SUCCEEDED",
            detail="revision integrity and baseline-v1 content policy validated",
        )


class PublishSnapshotValidationHandler:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def execute(self, request: OperationExecutionRequest) -> OperationItemResultUpdate:
        strict = request.parameters.get("strict", False)
        if not isinstance(strict, bool):
            return OperationItemResultUpdate(
                status="FAILED",
                errorCode="INVALID_STRICT_PARAMETER",
                detail="strict must be a boolean",
            )
        async with self.database.unit_of_work() as session:
            plan = await session.scalar(
                select(PublishPlanRow).where(
                    PublishPlanRow.id == request.resource_id,
                    PublishPlanRow.tenant_id == request.tenant_id,
                )
            )
            if plan is None:
                return OperationItemResultUpdate(
                    status="FAILED",
                    errorCode="PUBLISH_PLAN_NOT_FOUND",
                    detail="publish plan does not exist in the operation tenant",
                )
            snapshot = await session.scalar(
                select(PublishSnapshotRow).where(
                    PublishSnapshotRow.plan_id == plan.id,
                    PublishSnapshotRow.tenant_id == request.tenant_id,
                )
            )
            revision = await session.scalar(
                select(ContentRevisionRow).where(
                    ContentRevisionRow.id == plan.content_revision_id,
                    ContentRevisionRow.tenant_id == request.tenant_id,
                )
            )
            automation = await session.scalar(
                select(AutomationVersionRow).where(
                    AutomationVersionRow.id == plan.automation_package_version_id,
                    AutomationVersionRow.tenant_id == request.tenant_id,
                )
            )
            if snapshot is None or revision is None or automation is None:
                return OperationItemResultUpdate(
                    status="FAILED",
                    errorCode="SNAPSHOT_REFERENCE_MISSING",
                    detail="snapshot, revision, or automation reference is missing",
                )
            if canonical_hash(revision.payload) != revision.payload_sha256:
                return OperationItemResultUpdate(
                    status="FAILED",
                    errorCode="REVISION_INTEGRITY_MISMATCH",
                    detail="snapshot references a revision with an invalid digest",
                )
            if canonical_hash(snapshot.payload) != snapshot.payload_sha256:
                return OperationItemResultUpdate(
                    status="FAILED",
                    errorCode="SNAPSHOT_INTEGRITY_MISMATCH",
                    detail="stored snapshot payload does not match its immutable digest",
                )
            expected_payload = {
                "platform": plan.platform,
                "contentRevision": {
                    "id": revision.id,
                    "payload": revision.payload,
                    "sha256": revision.payload_sha256,
                },
                "automationPackage": {
                    "id": automation.id,
                    "name": automation.name,
                    "version": automation.version,
                    "sha256": automation.artifact_sha256,
                },
                "schedule": plan.schedule,
                "execution": plan.execution,
                "targets": plan.targets,
                "approvalPolicy": plan.approval_policy,
            }
            if (
                snapshot.plan_id != plan.id
                or snapshot.content_revision_id != revision.id
                or snapshot.automation_package_version_id != automation.id
                or snapshot.payload != expected_payload
            ):
                return OperationItemResultUpdate(
                    status="FAILED",
                    errorCode="SNAPSHOT_REFERENCE_MISMATCH",
                    detail="snapshot fields do not match the frozen publish plan references",
                )
            if plan.cancel_requested:
                return OperationItemResultUpdate(
                    status="BLOCKED",
                    errorCode="PUBLISH_PLAN_CANCELED",
                    detail="publish plan cancellation was requested",
                )
            if strict and not automation.production_qualified:
                return OperationItemResultUpdate(
                    status="BLOCKED",
                    errorCode="AUTOMATION_NOT_PRODUCTION_QUALIFIED",
                    detail="strict validation requires a production-qualified automation package",
                )
        return OperationItemResultUpdate(
            status="SUCCEEDED",
            detail="publish snapshot integrity and frozen references validated",
        )


class OperationExecutionSink:
    """Idempotently consumes eligible operation task events."""

    def __init__(
        self,
        database: Database,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.database = database
        self.registry = OperationExecutorRegistry(settings)
        self._owns_client = client is None and bool(settings.operation_executor_urls)
        self._client = client
        self.handlers: dict[str, OperationHandler] = {
            "works.revision.validate": RevisionValidationHandler(database),
            "publish_plans.snapshot.validate": PublishSnapshotValidationHandler(database),
        }
        if settings.operation_executor_urls:
            token_setting = settings.operation_executor_bearer_token
            if token_setting is None:
                raise ValueError("operation executor bearer token is required")
            token = token_setting.get_secret_value().strip()
            if not token:
                raise ValueError("operation executor bearer token is empty")
            if self._client is None:
                self._client = httpx.AsyncClient(
                    timeout=settings.operation_executor_timeout_seconds,
                    follow_redirects=False,
                )
            for operation_key, endpoint in settings.operation_executor_urls.items():
                self.handlers[operation_key] = HttpOperationHandler(
                    endpoint,
                    token,
                    self._client,
                )

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def publish(self, event: EventEnvelope) -> None:
        if event.event_type not in EXECUTION_EVENT_TYPES:
            return
        if event.aggregate_type != "operation_task":
            raise ValueError("operation execution event has an invalid aggregate type")
        if event.payload.get("taskId") != event.aggregate_id:
            raise ValueError("operation execution event taskId does not match aggregateId")

        task_state = await self._task_state(event)
        if task_state is None or task_state[1] in TERMINAL_TASK_STATES:
            return
        operation_key, status = task_state
        if status == "PENDING_APPROVAL":
            return
        handler = self.handlers.get(operation_key)
        if handler is None:
            await self._audit_executor_unavailable(event, operation_key)
            raise OperationExecutorUnavailable(
                f"no deployed executor is configured for {operation_key}"
            )

        item_ids = await self._item_ids(event)
        for item_id in item_ids:
            request = await self._claim_item(event, item_id)
            if request is None:
                continue
            try:
                result = await handler.execute(request)
            except Exception as exc:
                await self._record_retry(request, exc)
                raise
            await self._record_result(request, result)

    async def _task_state(self, event: EventEnvelope) -> tuple[str, str] | None:
        async with self.database.unit_of_work() as session:
            row = await session.execute(
                select(OperationTaskRow.operation_key, OperationTaskRow.status).where(
                    OperationTaskRow.id == event.aggregate_id,
                    OperationTaskRow.tenant_id == event.tenant_id,
                )
            )
            value = row.one_or_none()
            return None if value is None else (value[0], value[1])

    async def _item_ids(self, event: EventEnvelope) -> list[str]:
        async with self.database.unit_of_work() as session:
            rows = await session.scalars(
                select(OperationItemRow.id)
                .where(
                    OperationItemRow.task_id == event.aggregate_id,
                    OperationItemRow.tenant_id == event.tenant_id,
                )
                .order_by(OperationItemRow.resource_id)
            )
            return list(rows)

    async def _claim_item(
        self, event: EventEnvelope, item_id: str
    ) -> OperationExecutionRequest | None:
        actor = _service_actor(event.tenant_id, event.id)
        async with self.database.unit_of_work() as session:
            task = await session.scalar(
                select(OperationTaskRow)
                .where(
                    OperationTaskRow.id == event.aggregate_id,
                    OperationTaskRow.tenant_id == event.tenant_id,
                )
                .with_for_update()
            )
            item = await session.scalar(
                select(OperationItemRow)
                .where(
                    OperationItemRow.id == item_id,
                    OperationItemRow.task_id == event.aggregate_id,
                    OperationItemRow.tenant_id == event.tenant_id,
                )
                .with_for_update()
            )
            if task is None or item is None:
                raise RuntimeError("operation task or item disappeared before execution")
            if (
                task.status in TERMINAL_TASK_STATES
                or task.status == "PENDING_APPROVAL"
                or task.cancel_requested
                or item.status in TERMINAL_ITEM_STATES
            ):
                return None
            if item.status not in {"QUEUED", "RUNNING"}:
                raise RuntimeError(f"operation item has unsupported state {item.status}")

            control = ControlRepository(session, actor)
            action = (
                "operation.item.execution_started"
                if item.status == "QUEUED"
                else "operation.item.execution_replayed"
            )
            now = datetime.now(UTC)
            if item.status == "QUEUED":
                item.status = "RUNNING"
                item.updated_at = now
            if task.started_at is None:
                task.started_at = now
            task.status = "RUNNING"
            control.audit(
                action=action,
                resource_type="operation_task",
                resource_id=task.id,
                after={"resource_id": item.resource_id, "status": item.status},
                result="RUNNING",
                metadata={"event_id": event.id, "operation_key": task.operation_key},
            )
            return OperationExecutionRequest(
                event_id=event.id,
                tenant_id=event.tenant_id,
                task_id=task.id,
                item_id=item.id,
                operation_key=task.operation_key,
                resource_id=item.resource_id,
                parameters=dict(task.parameters),
                context=dict(task.context),
            )

    async def _record_result(
        self,
        request: OperationExecutionRequest,
        result: OperationItemResultUpdate,
    ) -> None:
        actor = _service_actor(request.tenant_id, request.event_id)
        async with self.database.unit_of_work() as session:
            task = await session.scalar(
                select(OperationTaskRow)
                .where(
                    OperationTaskRow.id == request.task_id,
                    OperationTaskRow.tenant_id == request.tenant_id,
                )
                .with_for_update()
            )
            item = await session.scalar(
                select(OperationItemRow)
                .where(
                    OperationItemRow.id == request.item_id,
                    OperationItemRow.tenant_id == request.tenant_id,
                )
                .with_for_update()
            )
            if task is None or item is None:
                raise RuntimeError("operation task or item disappeared before result persistence")
            control = ControlRepository(session, actor)
            if task.cancel_requested or task.status == "CANCELED" or item.status == "CANCELED":
                control.audit(
                    action="operation.item.late_result_discarded",
                    resource_type="operation_task",
                    resource_id=task.id,
                    after={"resource_id": item.resource_id, "discarded_status": result.status},
                    result="CANCELED",
                    metadata={"event_id": request.event_id},
                )
                return
            if item.status in TERMINAL_ITEM_STATES:
                if OperationService._same_result(item, result):
                    return
                control.audit(
                    action="operation.item.conflicting_result_discarded",
                    resource_type="operation_task",
                    resource_id=task.id,
                    after={"resource_id": item.resource_id, "discarded_status": result.status},
                    result="FAILED",
                    metadata={"event_id": request.event_id},
                )
                return

            item.status = result.status
            item.error_code = result.error_code
            item.detail = result.detail
            item.evidence_refs = list(result.evidence_refs)
            item.updated_at = datetime.now(UTC)
            items = list(
                await session.scalars(
                    select(OperationItemRow)
                    .where(
                        OperationItemRow.task_id == task.id,
                        OperationItemRow.tenant_id == request.tenant_id,
                    )
                    .with_for_update()
                )
            )
            OperationService._recalculate(task, items)
            control.audit(
                action="operation.item.result_recorded",
                resource_type="operation_task",
                resource_id=task.id,
                after={
                    "resource_id": item.resource_id,
                    "status": result.status,
                    "error_code": result.error_code,
                    "evidence_count": len(result.evidence_refs),
                },
                result=result.status,
                metadata={"event_id": request.event_id, "executor": "restricted_consumer"},
            )
            control.emit(
                control.event(
                    "operation_task",
                    task.id,
                    "operation.task.updated",
                    {"taskId": task.id, "status": task.status, "resourceId": item.resource_id},
                )
            )

    async def _record_retry(
        self,
        request: OperationExecutionRequest,
        error: Exception,
    ) -> None:
        actor = _service_actor(request.tenant_id, request.event_id)
        async with self.database.unit_of_work() as session:
            task = await session.scalar(
                select(OperationTaskRow)
                .where(
                    OperationTaskRow.id == request.task_id,
                    OperationTaskRow.tenant_id == request.tenant_id,
                )
                .with_for_update()
            )
            if task is None:
                return
            ControlRepository(session, actor).audit(
                action="operation.item.execution_retry_scheduled",
                resource_type="operation_task",
                resource_id=task.id,
                after={"resource_id": request.resource_id, "status": task.status},
                result="FAILED",
                metadata={"event_id": request.event_id, "error_type": type(error).__name__},
            )

    async def _audit_executor_unavailable(self, event: EventEnvelope, operation_key: str) -> None:
        actor = _service_actor(event.tenant_id, event.id)
        async with self.database.unit_of_work() as session:
            ControlRepository(session, actor).audit(
                action="operation.task.executor_unavailable",
                resource_type="operation_task",
                resource_id=event.aggregate_id,
                after={"operation_key": operation_key},
                result="FAILED",
                metadata={"event_id": event.id},
            )


def _service_actor(tenant_id: str, request_id: str) -> Actor:
    return Actor(
        tenant_id=uuid.UUID(tenant_id),
        user_id=SERVICE_USER_ID,
        roles=frozenset({Role.SYSTEM_SERVICE}),
        mfa=True,
        request_id=request_id,
    )


def _first_prohibited_field(value: Any, path: str = "payload") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("_", "").replace("-", "")
            if any(fragment in normalized for fragment in PROHIBITED_CONTENT_FIELDS):
                return f"{path}.{key}"
            result = _first_prohibited_field(child, f"{path}.{key}")
            if result is not None:
                return result
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result = _first_prohibited_field(child, f"{path}[{index}]")
            if result is not None:
                return result
    return None
