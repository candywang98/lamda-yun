from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from cloudctl_api.db import (
    AuditEventRow,
    ContentItemRow,
    ContentRevisionRow,
    Database,
    OperationItemRow,
    OperationTaskRow,
    OutboxEventRow,
)
from cloudctl_api.operation_service import OperationService
from cloudctl_api.settings import Settings
from cloudctl_domain import Actor, Role, canonical_hash
from cloudctl_outbox import InMemorySink, OperationExecutionSink, OutboxDispatcher
from cloudctl_outbox.store import OutboxStore
from cloudctl_outbox.temporal_sink import ControlApiPlanLoader, StaticAccessTokenProvider
from pydantic import SecretStr
from sqlalchemy import select

TENANT_ID = "00000000-0000-7000-8000-000000001111"
USER_ID = "00000000-0000-7000-8000-000000002222"


async def seed_operation_event(
    database: Database,
    *,
    operation_key: str,
    resource_id: str,
    status: str = "QUEUED",
    event_type: str = "operation.task.created",
    duplicate_event: bool = False,
) -> tuple[str, str, list[str]]:
    now = datetime.now(UTC)
    task_id = str(uuid.uuid4())
    item_id = str(uuid.uuid4())
    event_ids = [str(uuid.uuid4())]
    if duplicate_event:
        event_ids.append(str(uuid.uuid4()))
    async with database.unit_of_work() as session:
        session.add(
            OperationTaskRow(
                id=task_id,
                tenant_id=TENANT_ID,
                operation_key=operation_key,
                feature_id=None,
                module=operation_key.split(".", maxsplit=1)[0],
                idempotency_key=f"request-{task_id}",
                request_sha256=canonical_hash({"operationKey": operation_key}),
                requested_by=USER_ID,
                status=status,
                parameters={},
                context={},
                total_count=1,
                succeeded_count=0,
                failed_count=0,
                blocked_count=0,
                canceled_count=0,
                cancel_requested=False,
                result_summary={},
                started_at=None,
                completed_at=None,
                approval_decision="APPROVED" if event_type.endswith("approved") else None,
                approval_reason=None,
                approved_by=None,
                decided_at=None,
                created_at=now,
            )
        )
        session.add(
            OperationItemRow(
                id=item_id,
                tenant_id=TENANT_ID,
                task_id=task_id,
                resource_id=resource_id,
                status="QUEUED",
                error_code=None,
                detail=None,
                evidence_refs=[],
                updated_at=now,
            )
        )
        for event_id in event_ids:
            session.add(
                OutboxEventRow(
                    id=event_id,
                    tenant_id=TENANT_ID,
                    aggregate_type="operation_task",
                    aggregate_id=task_id,
                    event_type=event_type,
                    payload={
                        "taskId": task_id,
                        "operationKey": operation_key,
                        "status": status,
                    },
                    occurred_at=now,
                    published_at=None,
                    claimed_at=None,
                    claim_owner=None,
                    attempts=0,
                    last_error=None,
                )
            )
    return task_id, item_id, event_ids


@pytest.mark.asyncio
async def test_outbox_claim_dispatch_and_consumer_deduplication() -> None:
    database = Database(Settings(env="test", repository_mode="memory"))
    await database.create_schema()
    event_id = str(uuid.uuid4())
    async with database.unit_of_work() as session:
        session.add(
            OutboxEventRow(
                id=event_id,
                tenant_id=str(uuid.uuid4()),
                aggregate_type="publish_plan",
                aggregate_id=str(uuid.uuid4()),
                event_type="publish.plan.submitted",
                payload={"requiresApproval": False},
                occurred_at=datetime.now(UTC),
                published_at=None,
                claimed_at=None,
                claim_owner=None,
                attempts=0,
                last_error=None,
            )
        )
    sink = InMemorySink()
    dispatcher = OutboxDispatcher(OutboxStore(database), sink, owner="test-dispatcher")
    assert await dispatcher.dispatch_once() == 1
    assert await dispatcher.dispatch_once() == 0
    assert [event.id for event in sink.events] == [event_id]
    await database.dispose()


@pytest.mark.asyncio
async def test_control_api_plan_loader_uses_bearer_service_authentication() -> None:
    def load_plan(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer service-access-token"
        for forbidden in ("X-Tenant-Id", "X-User-Id", "X-Roles", "X-MFA"):
            assert forbidden not in request.headers
        return httpx.Response(
            200,
            json={
                "snapshot": {"id": "snapshot-1"},
                "publishTargets": [
                    {"id": "target-1", "device_id": "device-1"},
                ],
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(load_plan),
        base_url="https://control-api.example.test",
    ) as client:
        loader = ControlApiPlanLoader(
            "https://control-api.example.test",
            StaticAccessTokenProvider("service-access-token"),
            client,
        )
        loaded = await loader.load("tenant-1", "plan-1")

    assert loaded.plan_id == "plan-1"
    assert loaded.targets[0].tenant_id == "tenant-1"
    assert loaded.targets[0].device_id == "device-1"


@pytest.mark.asyncio
async def test_control_api_plan_loader_rejects_empty_service_token() -> None:
    async with httpx.AsyncClient(
        base_url="https://control-api.example.test", trust_env=False
    ) as client:
        loader = ControlApiPlanLoader(
            "https://control-api.example.test",
            StaticAccessTokenProvider("   "),
            client,
        )
        with pytest.raises(ValueError, match="access token is empty"):
            await loader.load("tenant-1", "plan-1")


@pytest.mark.asyncio
async def test_operation_consumer_executes_builtin_revision_validation_and_audits() -> None:
    settings = Settings(env="test", repository_mode="memory")
    database = Database(settings)
    await database.create_schema()
    revision_id = str(uuid.uuid4())
    payload = {"title": "authorized listing", "body": "validated locally"}
    now = datetime.now(UTC)
    async with database.unit_of_work() as session:
        content_id = str(uuid.uuid4())
        session.add(
            ContentItemRow(
                id=content_id,
                tenant_id=TENANT_ID,
                title="authorized listing",
                created_by=USER_ID,
                created_at=now,
            )
        )
        session.add(
            ContentRevisionRow(
                id=revision_id,
                tenant_id=TENANT_ID,
                content_id=content_id,
                revision_no=1,
                payload=payload,
                payload_sha256=canonical_hash(payload),
                created_by=USER_ID,
                created_at=now,
            )
        )
    task_id, _, _ = await seed_operation_event(
        database,
        operation_key="works.revision.validate",
        resource_id=revision_id,
    )
    sink = OperationExecutionSink(database, settings)
    dispatcher = OutboxDispatcher(OutboxStore(database), sink, owner="operation-consumer")

    assert await dispatcher.dispatch_once() == 1
    async with database.unit_of_work() as session:
        task = await session.get(OperationTaskRow, task_id)
        assert task is not None
        assert task.status == "SUCCEEDED"
        item = await session.scalar(
            select(OperationItemRow).where(OperationItemRow.task_id == task_id)
        )
        assert item is not None
        assert item.status == "SUCCEEDED"
        audits = list(
            await session.scalars(
                select(AuditEventRow)
                .where(AuditEventRow.resource_id == task_id)
                .order_by(AuditEventRow.occurred_at)
            )
        )
        assert [audit.action for audit in audits] == [
            "operation.item.execution_started",
            "operation.item.result_recorded",
        ]
        assert {audit.actor_type for audit in audits} == {"service"}
    await sink.close()
    await database.dispose()


@pytest.mark.asyncio
async def test_operation_consumer_uses_fixed_http_contract_and_deduplicates_events() -> None:
    calls: list[httpx.Request] = []

    async def execute(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = json.loads(request.content)
        assert set(body) == {
            "taskId",
            "itemId",
            "tenantId",
            "operationKey",
            "resourceId",
            "parameters",
            "context",
        }
        assert request.headers["Authorization"] == "Bearer adapter-token"
        assert request.headers["Idempotency-Key"] == f"{body['taskId']}:{body['itemId']}"
        return httpx.Response(200, json={"status": "SUCCEEDED", "detail": "generated"})

    settings = Settings(
        env="test",
        repository_mode="memory",
        operation_executor_urls={
            "media.derivative.generate": "https://executor.example.test/v1/media/derivative"
        },
        operation_executor_bearer_token=SecretStr("adapter-token"),
    )
    database = Database(settings)
    await database.create_schema()
    task_id, _, event_ids = await seed_operation_event(
        database,
        operation_key="media.derivative.generate",
        resource_id="media-1",
        duplicate_event=True,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(execute)) as client:
        sink = OperationExecutionSink(database, settings, client)
        dispatcher = OutboxDispatcher(OutboxStore(database), sink, owner="http-operation-consumer")
        assert await dispatcher.dispatch_once() == 2

    assert len(calls) == 1
    async with database.unit_of_work() as session:
        task = await session.get(OperationTaskRow, task_id)
        assert task is not None and task.status == "SUCCEEDED"
        events = [await session.get(OutboxEventRow, event_id) for event_id in event_ids]
        assert all(event is not None and event.published_at is not None for event in events)
    await database.dispose()


@pytest.mark.asyncio
async def test_unconfigured_operation_keeps_outbox_event_retryable() -> None:
    settings = Settings(env="test", repository_mode="memory")
    database = Database(settings)
    await database.create_schema()
    task_id, _, event_ids = await seed_operation_event(
        database,
        operation_key="media.derivative.generate",
        resource_id="media-1",
    )
    sink = OperationExecutionSink(database, settings)
    dispatcher = OutboxDispatcher(OutboxStore(database), sink, owner="missing-operation-consumer")

    assert await dispatcher.dispatch_once() == 0
    async with database.unit_of_work() as session:
        event = await session.get(OutboxEventRow, event_ids[0])
        task = await session.get(OperationTaskRow, task_id)
        assert event is not None
        assert event.published_at is None
        assert event.claim_owner is None
        assert event.last_error == "OperationExecutorUnavailable"
        assert task is not None and task.status == "QUEUED"
    await sink.close()
    await database.dispose()


@pytest.mark.asyncio
async def test_running_operation_cancel_discards_late_adapter_result(tmp_path: Path) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def delayed_result(_: httpx.Request) -> httpx.Response:
        started.set()
        await release.wait()
        return httpx.Response(200, json={"status": "SUCCEEDED", "detail": "too late"})

    settings = Settings(
        env="test",
        repository_mode="sqlite",
        sqlite_path=tmp_path / "operation-cancel.db",
        operation_executor_urls={
            "media.derivative.generate": "https://executor.example.test/v1/media/derivative"
        },
        operation_executor_bearer_token=SecretStr("adapter-token"),
    )
    database = Database(settings)
    await database.create_schema()
    task_id, _, _ = await seed_operation_event(
        database,
        operation_key="media.derivative.generate",
        resource_id="media-1",
    )
    actor = Actor(
        tenant_id=uuid.UUID(TENANT_ID),
        user_id=uuid.UUID(USER_ID),
        roles=frozenset({Role.CONTENT_EDITOR}),
        mfa=True,
        request_id=str(uuid.uuid4()),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(delayed_result)) as client:
        sink = OperationExecutionSink(database, settings, client)
        dispatcher = OutboxDispatcher(
            OutboxStore(database), sink, owner="cancel-operation-consumer"
        )
        dispatch = asyncio.create_task(dispatcher.dispatch_once())
        await asyncio.wait_for(started.wait(), timeout=5)
        canceled = await OperationService(database, settings).cancel_task(
            actor, task_id, "request withdrawn during execution"
        )
        assert canceled["status"] == "CANCELED"
        assert canceled["items"][0]["status"] == "CANCELED"
        release.set()
        assert await asyncio.wait_for(dispatch, timeout=5) == 1

    async with database.unit_of_work() as session:
        task = await session.get(OperationTaskRow, task_id)
        item = await session.scalar(
            select(OperationItemRow).where(OperationItemRow.task_id == task_id)
        )
        assert task is not None and task.status == "CANCELED"
        assert item is not None and item.status == "CANCELED"
        actions = list(
            await session.scalars(
                select(AuditEventRow.action).where(AuditEventRow.resource_id == task_id)
            )
        )
        assert "operation.task.canceled" in actions
        assert "operation.item.late_result_discarded" in actions
    await database.dispose()
