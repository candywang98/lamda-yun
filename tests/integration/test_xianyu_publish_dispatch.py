"""Dispatch-boundary regression tests for the Xianyu publish queue."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import socket
import subprocess
import uuid
from collections.abc import AsyncIterator
from typing import Any

import cloudctl_api.xianyu_publish as xianyu_publish
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


def identity(role: str = "device_operator") -> dict[str, str]:
    return {
        "X-Tenant-Id": TENANT,
        "X-User-Id": OPERATOR,
        "X-Roles": role,
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
    client: httpx.AsyncClient,
    queue_id: str,
    *,
    item_count: int = 2,
    with_media: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    device_id, account_id = await setup_device_and_account(client, queue_id)
    media: dict[str, Any] = {}
    if with_media:
        asset = await client.post(
            "/api/v1/media/assets:register",
            headers=identity("content_editor"),
            json={
                "sha256": hashlib.sha256(queue_id.encode()).hexdigest(),
                "objectKey": f"tenant/publish/{queue_id}.jpg",
                "contentType": "image/jpeg",
                "sizeBytes": 12,
            },
        )
        assert asset.status_code == 201, asset.text
        media = {
            "mediaAssetIds": [asset.json()["id"]],
            "deliveryId": str(uuid.uuid4()),
        }
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
                    **media,
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


async def dispatch_task_count(app: FastAPI, target_id: str) -> int:
    async with app.state.database.unit_of_work() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(MobileTaskRow)
                .where(
                    MobileTaskRow.tenant_id == TENANT,
                    MobileTaskRow.idempotency_key.like(f"xianyu-publish:{target_id}:%"),
                )
            )
            or 0
        )


async def dispatched_audit_count(app: FastAPI, target_id: str) -> int:
    async with app.state.database.unit_of_work() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(AuditEventRow)
                .where(
                    AuditEventRow.tenant_id == TENANT,
                    AuditEventRow.resource_id == target_id,
                    AuditEventRow.action == "xianyu.publish.dispatched",
                )
            )
            or 0
        )


async def enroll_companion(
    client: httpx.AsyncClient, device_id: str, suffix: str
) -> dict[str, str]:
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
            "appInstanceId": suffix,
            "companionVersion": "1.0.0",
        },
    )
    assert enrolled.status_code == 201, enrolled.text
    return {"Authorization": f"Bearer {enrolled.json()['bindingToken']}"}


@pytest.mark.asyncio
async def test_new_dispatch_snapshot_hash_matches_canonical_payload(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = api
    _, targets = await create_queue(client, "dispatch-snapshot", item_count=1)
    target = targets[0]
    dispatch = await client.post(
        f"/api/v1/xianyu/publish/queues/dispatch-snapshot/targets/{target['targetId']}/dispatch",
        headers=identity(),
    )
    assert dispatch.status_code == 200, dispatch.text
    task = await client.get(
        f"/api/v1/platform-tasks/{dispatch.json()['taskId']}", headers=identity()
    )
    assert task.status_code == 200, task.text
    payload = dict(task.json()["commandPayload"])
    snapshot_sha256 = payload.pop("snapshotSha256")
    expected = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    assert payload["completionBoundary"] == target["claimedBoundary"]
    assert snapshot_sha256 == expected


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
async def test_postgres_task_is_not_visible_or_claimable_before_queue_commit(
    postgres_pair: list[tuple[httpx.AsyncClient, FastAPI]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (first_client, first_app), (second_client, second_app) = postgres_pair
    device_id, targets = await create_queue(first_client, "dispatch-precommit", item_count=1)
    target = targets[0]
    companion_auth = await enroll_companion(first_client, device_id, "dispatch-precommit-instance")
    created_in_transaction = asyncio.Event()
    release_commit = asyncio.Event()
    original_create = first_app.state.platform_task_service.create

    async def block_before_queue_commit(*args: Any, **kwargs: Any):
        result = await original_create(*args, **kwargs)
        created_in_transaction.set()
        await release_commit.wait()
        return result

    monkeypatch.setattr(first_app.state.platform_task_service, "create", block_before_queue_commit)
    path = f"/api/v1/xianyu/publish/queues/dispatch-precommit/targets/{target['targetId']}/dispatch"
    dispatch_request = asyncio.create_task(first_client.post(path, headers=identity()))
    await asyncio.wait_for(created_in_transaction.wait(), timeout=5)

    visible_before_commit = await dispatch_task_count(second_app, target["targetId"])
    claim_request = asyncio.create_task(
        second_client.post(
            "/companion/v2/tasks/claim",
            headers=companion_auth,
            json={"leaseSeconds": 60},
        )
    )
    done, _pending = await asyncio.wait({claim_request}, timeout=0.2)

    release_commit.set()
    dispatch, claimed = await asyncio.gather(dispatch_request, claim_request)
    assert visible_before_commit == 0
    assert not done, "claim crossed the uncommitted queue transaction"
    assert dispatch.status_code == 200, dispatch.text
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["taskId"] == dispatch.json()["taskId"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_stage",
    ["after_insert", "after_snapshot_stamp", "after_target_audit"],
)
async def test_postgres_dispatch_failure_rolls_back_task_link_and_audit(
    postgres_pair: list[tuple[httpx.AsyncClient, FastAPI]],
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    (first_client, first_app), (second_client, second_app) = postgres_pair
    queue_id = {
        "after_insert": "dispatch-rb-insert",
        "after_snapshot_stamp": "dispatch-rb-stamp",
        "after_target_audit": "dispatch-rb-audit",
    }[failure_stage]
    device_id, targets = await create_queue(first_client, queue_id, item_count=1)
    target = targets[0]
    companion_auth = await enroll_companion(first_client, device_id, f"{queue_id}-instance")

    if failure_stage == "after_insert":
        service = first_app.state.platform_task_service.mobile
        original = service._insert_task

        async def fail_after_insert(*args: Any, **kwargs: Any):
            await original(*args, **kwargs)
            raise ValidationError("synthetic failure after task insert")

        monkeypatch.setattr(service, "_insert_task", fail_after_insert)
    elif failure_stage == "after_snapshot_stamp":
        service = first_app.state.platform_task_service
        original = service._stamp_business_fields

        async def fail_after_snapshot_stamp(*args: Any, **kwargs: Any):
            await original(*args, **kwargs)
            raise ValidationError("synthetic failure after snapshot stamp")

        monkeypatch.setattr(service, "_stamp_business_fields", fail_after_snapshot_stamp)
    else:
        original_audit = xianyu_publish._audit

        def fail_after_target_audit(*args: Any, **kwargs: Any) -> None:
            original_audit(*args, **kwargs)
            raise ValidationError("synthetic failure after target and audit mutation")

        monkeypatch.setattr(xianyu_publish, "_audit", fail_after_target_audit)

    failed = await first_client.post(
        f"/api/v1/xianyu/publish/queues/{queue_id}/targets/{target['targetId']}/dispatch",
        headers=identity(),
    )
    assert failed.status_code == 422, failed.text
    queue = (
        await second_client.get(f"/api/v1/xianyu/publish/queues/{queue_id}", headers=identity())
    ).json()
    assert queue["targets"][0]["state"] == "PENDING"
    assert queue["targets"][0]["taskIds"] == []
    assert await dispatch_task_count(second_app, target["targetId"]) == 0
    assert await dispatched_audit_count(second_app, target["targetId"]) == 0
    claim = await second_client.post(
        "/companion/v2/tasks/claim",
        headers=companion_auth,
        json={"leaseSeconds": 60},
    )
    assert claim.status_code == 204, claim.text


@pytest.mark.asyncio
async def test_postgres_caller_owned_flush_integrity_error_maps_to_conflict_and_rolls_back(
    postgres_pair: list[tuple[httpx.AsyncClient, FastAPI]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (first_client, first_app), (second_client, second_app) = postgres_pair
    _, targets = await create_queue(first_client, "dispatch-flush-conflict", item_count=1)
    target = targets[0]
    service = first_app.state.platform_task_service.mobile

    async def fail_caller_owned_flush(*args: Any, **kwargs: Any):
        session = kwargs["session"]
        session.add(MobileTaskRow(id=str(uuid.uuid4())))
        await session.flush()
        raise AssertionError("database constraint violation did not fail the flush")

    monkeypatch.setattr(service, "_insert_task", fail_caller_owned_flush)
    failed = await first_client.post(
        "/api/v1/xianyu/publish/queues/dispatch-flush-conflict/targets/"
        f"{target['targetId']}/dispatch",
        headers=identity(),
    )
    assert failed.status_code == 409, failed.text
    assert failed.json()["detail"] == "task idempotency conflict"
    queue = (
        await second_client.get(
            "/api/v1/xianyu/publish/queues/dispatch-flush-conflict", headers=identity()
        )
    ).json()
    assert queue["targets"][0]["state"] == "PENDING"
    assert queue["targets"][0]["taskIds"] == []
    assert await dispatch_task_count(second_app, target["targetId"]) == 0
    assert await dispatched_audit_count(second_app, target["targetId"]) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("with_media", [False, True], ids=["text-only", "media"])
async def test_postgres_success_commits_one_fully_frozen_linked_task(
    postgres_pair: list[tuple[httpx.AsyncClient, FastAPI]],
    with_media: bool,
) -> None:
    (first_client, _first_app), (second_client, second_app) = postgres_pair
    queue_id = f"dispatch-success-{'media' if with_media else 'text'}"
    _, targets = await create_queue(first_client, queue_id, item_count=1, with_media=with_media)
    target = targets[0]
    dispatched = await first_client.post(
        f"/api/v1/xianyu/publish/queues/{queue_id}/targets/{target['targetId']}/dispatch",
        headers=identity(),
    )
    assert dispatched.status_code == 200, dispatched.text

    queue = (
        await second_client.get(f"/api/v1/xianyu/publish/queues/{queue_id}", headers=identity())
    ).json()
    committed_target = queue["targets"][0]
    task_id = dispatched.json()["taskId"]
    assert committed_target["state"] == "IN_FLIGHT"
    assert committed_target["taskIds"] == [task_id]
    assert await dispatch_task_count(second_app, target["targetId"]) == 1
    assert await dispatched_audit_count(second_app, target["targetId"]) == 1

    task = await second_client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert task.status_code == 200, task.text
    payload = dict(task.json()["commandPayload"])
    stored_hash = payload.pop("snapshotSha256")
    assert payload["completionBoundary"] == target["claimedBoundary"]
    assert (
        stored_hash
        == hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
    )
    if with_media:
        assert payload["parameters"]["mediaAssetIds"]
        assert payload["mediaDeliveryId"]
    else:
        assert "mediaAssetIds" not in payload["parameters"]
        assert payload["mediaDeliveryId"] is None


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
async def test_lost_http_response_after_commit_does_not_mint_another_task(
    postgres_pair: list[tuple[httpx.AsyncClient, FastAPI]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (first_client, first_app), (second_client, second_app) = postgres_pair
    _, targets = await create_queue(first_client, "dispatch-lost-response", item_count=1)
    target_id = targets[0]["targetId"]
    original_dispatch = xianyu_publish.XianyuPublishQueueService.dispatch

    async def lose_response_after_commit(*args: Any, **kwargs: Any):
        await original_dispatch(*args, **kwargs)
        raise ValidationError("synthetic response loss after commit")

    monkeypatch.setattr(
        xianyu_publish.XianyuPublishQueueService,
        "dispatch",
        lose_response_after_commit,
    )
    path = f"/api/v1/xianyu/publish/queues/dispatch-lost-response/targets/{target_id}/dispatch"
    failed = await first_client.post(path, headers=identity())
    assert failed.status_code == 422, failed.text
    monkeypatch.setattr(xianyu_publish.XianyuPublishQueueService, "dispatch", original_dispatch)

    retry = await second_client.post(path, headers=identity())
    assert retry.status_code == 409, retry.text
    queue = (
        await second_client.get(
            "/api/v1/xianyu/publish/queues/dispatch-lost-response", headers=identity()
        )
    ).json()
    assert queue["targets"][0]["state"] == "IN_FLIGHT"
    assert len(queue["targets"][0]["taskIds"]) == 1
    assert await dispatch_task_count(second_app, target_id) == 1
    assert await dispatched_audit_count(second_app, target_id) == 1


@pytest.mark.asyncio
async def test_legacy_paused_orphan_is_recovered_without_mutation(
    postgres_pair: list[tuple[httpx.AsyncClient, FastAPI]],
) -> None:
    (first_client, first_app), (second_client, second_app) = postgres_pair
    device_id, targets = await create_queue(first_client, "dispatch-legacy", item_count=1)
    target = targets[0]
    target_id = target["targetId"]
    dispatch_key = f"xianyu-publish:{target_id}:1"
    created = await first_client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": dispatch_key},
        json={
            "deviceId": device_id,
            "accountId": target["accountId"],
            "commandType": "xianyu.publish_listing.v1",
            "parameters": {"listingBody": "dispatch item 0", "price": "1.00"},
            "publishTargetId": target_id,
            "batchId": "dispatch-legacy",
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["items"][0]["taskId"]

    companion_auth = await enroll_companion(first_client, device_id, "dispatch-legacy-instance")
    claimed = await second_client.post(
        "/companion/v2/tasks/claim",
        headers=companion_auth,
        json={"leaseSeconds": 60},
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["taskId"] == task_id
    paused = await second_client.post(
        f"/companion/v2/tasks/{task_id}/events",
        headers=companion_auth,
        json={
            "leaseId": claimed.json()["leaseId"],
            "sequence": 1,
            "eventType": "PAUSED_WAITING_USER",
            "stepIndex": 0,
            "payload": {"reason": "legacy orphan state must survive"},
        },
    )
    assert paused.status_code == 201, paused.text
    async with first_app.state.database.unit_of_work() as session:
        task_row = await session.get(MobileTaskRow, task_id, with_for_update=True)
        assert task_row is not None
        task_row.result = {"checkpoint": "preserve-legacy-orphan"}
    before = await first_client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert before.status_code == 200, before.text
    assert before.json()["state"] == "PAUSED_WAITING_USER"
    assert before.json()["controlMode"] == "REMOTE"
    assert "completionBoundary" not in before.json()["commandPayload"]

    recovered = await first_client.post(
        f"/api/v1/xianyu/publish/queues/dispatch-legacy/targets/{target_id}/dispatch",
        headers=identity(),
    )
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["state"] == "IN_FLIGHT"
    assert recovered.json()["taskId"] == task_id
    assert recovered.json()["taskIds"] == [task_id]
    assert await dispatch_task_count(second_app, target_id) == 1
    after = await second_client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert after.status_code == 200, after.text
    assert after.json()["state"] == "PAUSED_WAITING_USER"
    assert after.json()["controlMode"] == "REMOTE"
    assert after.json()["result"] == before.json()["result"]
    assert after.json()["commandPayload"] == before.json()["commandPayload"]
    assert after.json()["snapshotSha256"] == before.json()["snapshotSha256"]
    assert await dispatched_audit_count(second_app, target_id) == 1


@pytest.mark.asyncio
async def test_dispatch_recovery_fails_closed_on_partial_mismatching_task(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    device_id, targets = await create_queue(client, "dispatch-mismatch", item_count=1)
    target = targets[0]
    dispatch_key = f"xianyu-publish:{target['targetId']}:1"
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": dispatch_key},
        json={
            "deviceId": device_id,
            "accountId": target["accountId"],
            "commandType": "xianyu.publish_listing.v1",
            "parameters": {"listingBody": "dispatch item 0", "price": "1.00"},
            "publishTargetId": target["targetId"],
            "batchId": "dispatch-mismatch",
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["items"][0]["taskId"]
    corrupted_payload = {"publishTargetId": "wrong-target"}
    async with app.state.database.unit_of_work() as session:
        task_row = await session.get(MobileTaskRow, task_id, with_for_update=True)
        assert task_row is not None
        task_row.command_payload = corrupted_payload

    dispatch = await client.post(
        f"/api/v1/xianyu/publish/queues/dispatch-mismatch/targets/{target['targetId']}/dispatch",
        headers=identity(),
    )
    assert dispatch.status_code == 409, dispatch.text
    queue = (
        await client.get("/api/v1/xianyu/publish/queues/dispatch-mismatch", headers=identity())
    ).json()
    assert queue["targets"][0]["state"] == "PENDING"
    assert queue["targets"][0]["taskIds"] == []
    task = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert task.status_code == 200, task.text
    assert task.json()["state"] == "QUEUED"
    assert task.json()["controlMode"] == "AUTO"
    assert task.json()["commandPayload"] == corrupted_payload


@pytest.mark.asyncio
async def test_platform_task_idempotent_replay_preserves_started_task(
    api: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, app = api
    device_id, account_id = await setup_device_and_account(client, "platform-replay")
    task_body = {
        "deviceId": device_id,
        "accountId": account_id,
        "commandType": "xianyu.publish_listing.v1",
        "parameters": {"listingBody": "platform replay item", "price": "9.00"},
        "publishTargetId": "platform-replay-target",
        "batchId": "platform-replay",
    }
    task_headers = {**identity(), "Idempotency-Key": "platform-replay-preserves-state"}
    created = await client.post("/api/v1/platform-tasks", headers=task_headers, json=task_body)
    assert created.status_code == 201, created.text
    task_id = created.json()["items"][0]["taskId"]
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
            "appInstanceId": "platform-replay-instance",
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
    paused = await client.post(
        f"/companion/v2/tasks/{task_id}/events",
        headers=companion_auth,
        json={
            "leaseId": claimed.json()["leaseId"],
            "sequence": 1,
            "eventType": "PAUSED_WAITING_USER",
            "stepIndex": 0,
            "payload": {"reason": "idempotent replay must preserve state"},
        },
    )
    assert paused.status_code == 201, paused.text
    async with app.state.database.unit_of_work() as session:
        task_row = await session.get(MobileTaskRow, task_id, with_for_update=True)
        assert task_row is not None
        task_row.result = {"checkpoint": "platform-replay"}
    before = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert before.status_code == 200, before.text

    replay = await client.post("/api/v1/platform-tasks", headers=task_headers, json=task_body)
    assert replay.status_code == 200, replay.text
    assert replay.json()["items"][0]["taskId"] == task_id
    after = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
    assert after.status_code == 200, after.text
    assert after.json()["state"] == "PAUSED_WAITING_USER"
    assert after.json()["controlMode"] == "REMOTE"
    assert after.json()["result"] == before.json()["result"]
    assert after.json()["commandPayload"] == before.json()["commandPayload"]
    assert after.json()["snapshotSha256"] == before.json()["snapshotSha256"]


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
