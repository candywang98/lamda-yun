"""Dispatch-boundary regression tests for the Xianyu publish queue."""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.command_v1 import parse_command_v1
from cloudctl_api.db import AuditEventRow, MobileTaskRow
from cloudctl_api.settings import Settings
from cloudctl_domain import ValidationError
from fastapi import FastAPI
from sqlalchemy import func, select

TENANT = "00000000-0000-7000-8000-000000000111"
OPERATOR = "00000000-0000-7000-8000-000000000222"
POSTGRES_ENV = {**os.environ, "LC_ALL": "C", "LANG": "C", "LANGUAGE": "C"}


def identity() -> dict[str, str]:
    return {
        "X-Tenant-Id": TENANT,
        "X-User-Id": OPERATOR,
        "X-Roles": "device_operator",
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }


@pytest.fixture
async def api() -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, app


@pytest.fixture(scope="module")
def dispatch_postgres(tmp_path_factory):
    """Start a disposable PostgreSQL cluster; SQLite cannot prove row locking."""
    if not all(shutil.which(tool) for tool in ("initdb", "pg_ctl", "createdb")):
        pytest.skip("local PostgreSQL binaries unavailable")
    root = tmp_path_factory.mktemp("publish-dispatch-postgres")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
        ["initdb", "-D", str(root / "data"), "-A", "trust", "-U", "dispatchtest"],  # noqa: S607
        check=True,
        capture_output=True,
        env=POSTGRES_ENV,
    )
    subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
        [  # noqa: S607
            "pg_ctl",
            "-D",
            str(root / "data"),
            "-l",
            str(root / "server.log"),
            "-o",
            f"-h 127.0.0.1 -p {port} -c unix_socket_directories=''",
            "-w",
            "start",
        ],
        check=True,
        capture_output=True,
        env=POSTGRES_ENV,
    )
    try:
        yield port
    finally:
        subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
            ["pg_ctl", "-D", str(root / "data"), "-m", "immediate", "-w", "stop"],  # noqa: S607
            check=True,
            capture_output=True,
            env=POSTGRES_ENV,
        )


@pytest.fixture
def dispatch_pg_url(dispatch_postgres) -> str:
    name = "dispatch_" + uuid.uuid4().hex
    subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
        [  # noqa: S607
            "createdb",
            "-h",
            "127.0.0.1",
            "-p",
            str(dispatch_postgres),
            "-U",
            "dispatchtest",
            name,
        ],
        check=True,
        capture_output=True,
        env=POSTGRES_ENV,
    )
    return f"postgresql+asyncpg://dispatchtest@127.0.0.1:{dispatch_postgres}/{name}"


@pytest.fixture
async def postgres_pair(
    dispatch_pg_url: str,
) -> AsyncIterator[list[tuple[httpx.AsyncClient, FastAPI]]]:
    instances: list[tuple[httpx.AsyncClient, FastAPI]] = []
    contexts = []
    for _ in range(2):
        app = create_app(
            Settings(
                env="test",
                repository_mode="postgresql",
                database_url=dispatch_pg_url,
                dev_auth_bypass=True,
            )
        )
        await app.state.database.create_schema()
        context = app.router.lifespan_context(app)
        await context.__aenter__()
        contexts.append(context)
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        instances.append((client, app))
    try:
        yield instances
    finally:
        for client, _app in instances:
            await client.aclose()
        for context in contexts:
            await context.__aexit__(None, None, None)


async def setup_device_and_account(client: httpx.AsyncClient, suffix: str) -> tuple[str, str]:
    device = await client.post(
        "/api/v1/mobile/devices",
        headers=identity(),
        json={
            "logicalName": f"dispatch-{suffix}",
            "androidVersion": "14",
            "companionVersion": "1.0.0",
        },
    )
    assert device.status_code == 201, device.text
    account = await client.post(
        "/api/v1/accounts",
        headers=identity(),
        json={
            "platform": "xianyu",
            "externalSubjectRef": f"dispatch-{suffix}",
            "displayLabel": f"dispatch-{suffix}",
            "secretRef": f"vault://cloudctl/accounts/dispatch-{suffix}",
            "authorizationBasis": "Owner authorized the test account.",
        },
    )
    assert account.status_code == 201, account.text
    device_id = str(device.json()["id"])
    account_id = str(account.json()["id"])
    binding = await client.post(
        f"/api/v1/accounts/{account_id}/bindings",
        headers=identity(),
        json={"deviceId": device_id, "confirmationNote": "Owner confirmed."},
    )
    assert binding.status_code == 201, binding.text
    return device_id, account_id


async def create_queue(
    client: httpx.AsyncClient, queue_id: str, *, item_count: int = 2
) -> tuple[str, list[dict[str, Any]]]:
    device_id, account_id = await setup_device_and_account(client, queue_id)
    response = await client.post(
        "/api/v1/xianyu/publish/queues",
        headers=identity(),
        json={
            "queueId": queue_id,
            "deviceId": device_id,
            "accountId": account_id,
            "items": [
                {
                    "description": f"dispatch item {position}",
                    "price": f"{position + 1}.00",
                    "completionBoundary": "AUTO_FILL_HUMAN_COMMIT",
                }
                for position in range(item_count)
            ],
        },
    )
    assert response.status_code == 201, response.text
    return device_id, response.json()["targets"]


async def task_count(app: FastAPI, queue_id: str) -> int:
    async with app.state.database.unit_of_work() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(MobileTaskRow)
                .where(
                    MobileTaskRow.tenant_id == TENANT,
                    MobileTaskRow.batch_id == queue_id,
                )
            )
            or 0
        )


@pytest.mark.asyncio
async def test_direct_dispatch_cannot_skip_first_eligible_target(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    _, targets = await create_queue(client, "dispatch-skip")
    base = "/api/v1/xianyu/publish/queues/dispatch-skip"

    skipped = await client.post(
        f"{base}/targets/{targets[1]['targetId']}/dispatch", headers=identity()
    )
    assert skipped.status_code == 409, skipped.text
    queue = (await client.get(base, headers=identity())).json()
    assert [target["state"] for target in queue["targets"]] == ["PENDING", "PENDING"]
    assert await task_count(app, "dispatch-skip") == 0


@pytest.mark.asyncio
async def test_direct_dispatch_cannot_bypass_in_flight_after_next_returns_empty(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    _, targets = await create_queue(client, "dispatch-bypass")
    base = "/api/v1/xianyu/publish/queues/dispatch-bypass"

    first = await client.post(
        f"{base}/targets/{targets[0]['targetId']}/dispatch", headers=identity()
    )
    assert first.status_code == 200, first.text
    next_target = await client.post(f"{base}/next", headers=identity())
    assert next_target.status_code == 204, next_target.text
    bypassed = await client.post(
        f"{base}/targets/{targets[1]['targetId']}/dispatch", headers=identity()
    )
    assert bypassed.status_code == 409, bypassed.text
    queue = (await client.get(base, headers=identity())).json()
    assert [target["state"] for target in queue["targets"]] == ["IN_FLIGHT", "PENDING"]
    assert await task_count(app, "dispatch-bypass") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("second_position", [0, 1], ids=["same-target", "different-target"])
async def test_postgres_serializes_concurrent_dispatch_across_api_instances(
    postgres_pair: list[tuple[httpx.AsyncClient, FastAPI]],
    monkeypatch: pytest.MonkeyPatch,
    second_position: int,
) -> None:
    (first_client, first_app), (second_client, _second_app) = postgres_pair
    queue_id = f"dispatch-pg-{second_position}"
    _, targets = await create_queue(first_client, queue_id)
    entered_create = asyncio.Event()
    release_create = asyncio.Event()
    original_create = first_app.state.platform_task_service.create

    async def blocked_create(*args: Any, **kwargs: Any):
        entered_create.set()
        await release_create.wait()
        return await original_create(*args, **kwargs)

    monkeypatch.setattr(first_app.state.platform_task_service, "create", blocked_create)
    base = f"/api/v1/xianyu/publish/queues/{queue_id}/targets"
    first_request = asyncio.create_task(
        first_client.post(f"{base}/{targets[0]['targetId']}/dispatch", headers=identity())
    )
    await asyncio.wait_for(entered_create.wait(), timeout=5)
    second_request = asyncio.create_task(
        second_client.post(
            f"{base}/{targets[second_position]['targetId']}/dispatch", headers=identity()
        )
    )
    done, _pending = await asyncio.wait({second_request}, timeout=0.2)
    was_blocked = not done
    release_create.set()
    first, second = await asyncio.gather(first_request, second_request)

    assert was_blocked, "second API instance did not wait for the PostgreSQL queue lock"
    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    queue = (
        await second_client.get(f"/api/v1/xianyu/publish/queues/{queue_id}", headers=identity())
    ).json()
    assert [target["state"] for target in queue["targets"]] == ["IN_FLIGHT", "PENDING"]
    assert len(queue["targets"][0]["taskIds"]) == 1
    assert queue["targets"][1]["taskIds"] == []
    assert await task_count(first_app, queue_id) == 1


@pytest.mark.asyncio
async def test_task_create_commit_then_failure_recovers_same_dispatch_key(
    api: tuple[httpx.AsyncClient, FastAPI], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, app = api
    _, targets = await create_queue(client, "dispatch-recovery", item_count=1)
    target_id = targets[0]["targetId"]
    original_create = app.state.platform_task_service.create
    failed_once = False

    async def create_then_fail(*args: Any, **kwargs: Any):
        nonlocal failed_once
        views, created = await original_create(*args, **kwargs)
        if not failed_once:
            failed_once = True
            raise ValidationError("synthetic failure after task commit")
        return views, created

    monkeypatch.setattr(app.state.platform_task_service, "create", create_then_fail)
    path = f"/api/v1/xianyu/publish/queues/dispatch-recovery/targets/{target_id}/dispatch"
    failed = await client.post(path, headers=identity())
    assert failed.status_code == 422, failed.text
    queue = (
        await client.get("/api/v1/xianyu/publish/queues/dispatch-recovery", headers=identity())
    ).json()
    assert queue["targets"][0]["state"] == "PENDING"
    assert queue["targets"][0]["taskIds"] == []
    assert await task_count(app, "dispatch-recovery") == 1

    retry = await client.post(path, headers=identity())
    assert retry.status_code == 200, retry.text
    assert retry.json()["state"] == "IN_FLIGHT"
    assert retry.json()["taskIds"] == [retry.json()["taskId"]]
    assert await task_count(app, "dispatch-recovery") == 1


@pytest.mark.asyncio
async def test_dispatch_claim_pause_preserves_queue_identity_without_success_confirmation(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    device_id, targets = await create_queue(client, "dispatch-pause", item_count=1)
    target_id = targets[0]["targetId"]
    dispatch = await client.post(
        f"/api/v1/xianyu/publish/queues/dispatch-pause/targets/{target_id}/dispatch",
        headers=identity(),
    )
    assert dispatch.status_code == 200, dispatch.text
    task_id = dispatch.json()["taskId"]

    enrollment = await client.post(
        "/api/v1/mobile/enrollments",
        headers=identity(),
        json={"deviceId": device_id, "ttlSeconds": 600},
    )
    assert enrollment.status_code == 201, enrollment.text
    enrolled = await client.post(
        "/companion/v2/enroll",
        json={
            "code": enrollment.json()["code"],
            "appInstanceId": "dispatch-pause-instance",
            "companionVersion": "1.0.0",
        },
    )
    assert enrolled.status_code == 201, enrolled.text
    companion_auth = {"Authorization": f"Bearer {enrolled.json()['bindingToken']}"}
    claimed = await client.post(
        "/companion/v2/tasks/claim",
        headers=companion_auth,
        json={"leaseSeconds": 60},
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["taskId"] == task_id
    command = parse_command_v1(claimed.json()["command"])
    assert command["commandType"] == "xianyu.publish_listing.v1"
    async with app.state.database.unit_of_work() as session:
        task_row = await session.get(MobileTaskRow, task_id)
        assert task_row is not None
        assert not any(
            step.get("locatorRef") == "xianyu_publish_button" for step in list(task_row.steps or [])
        )

    paused = await client.post(
        f"/companion/v2/tasks/{task_id}/events",
        headers=companion_auth,
        json={
            "leaseId": claimed.json()["leaseId"],
            "sequence": 1,
            "eventType": "PAUSED_WAITING_USER",
            "stepIndex": 0,
            "payload": {"reason": "operator confirmation required"},
        },
    )
    assert paused.status_code == 201, paused.text

    task = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert task.status_code == 200, task.text
    assert task.json()["state"] == "PAUSED_WAITING_USER"
    assert task.json()["batchId"] == "dispatch-pause"
    assert task.json()["commandPayload"]["publishTargetId"] == target_id
    assert task.json()["runnerStatus"] != "SUCCEEDED"

    queue = (
        await client.get("/api/v1/xianyu/publish/queues/dispatch-pause", headers=identity())
    ).json()
    target = queue["targets"][0]
    assert target["state"] == "IN_FLIGHT"
    assert target["taskIds"] == [task_id]
    assert target["externalItemId"] is None
    assert target["recordedBoundary"] is None
    assert target["confirmedAt"] is None
    async with app.state.database.unit_of_work() as session:
        confirmations = await session.scalar(
            select(func.count())
            .select_from(AuditEventRow)
            .where(
                AuditEventRow.tenant_id == TENANT,
                AuditEventRow.resource_id == target_id,
                AuditEventRow.action == "xianyu.publish.confirmed",
            )
        )
    assert confirmations == 0
