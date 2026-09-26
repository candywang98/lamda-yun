"""A11 fleet claim/recovery regression tests (fleet-identity/v1@20260916.1 §7/§8).

Covers the frozen-steps (UNPINNED_STEPS_COMMANDS) claim → release → reclaim
cycle, the §7 immutable identity freeze {payloadIdentity,
commandRegistryVersion}, the §8 release/reclaim guards (PREFLIGHT-only
release before the first heartbeat, committed tasks are reconciled instead
of re-executed as fresh work), and the real-PostgreSQL concurrency proofs:
same-device concurrent claims across two API processes yield exactly one
holder, while different devices never wait on each other (per-device row
locks, no global claim lock).

The functional guards run on the in-memory SQLite app; the concurrency
proofs run exclusively against a disposable PostgreSQL cluster
(``isolated_postgres``) because SQLite cannot demonstrate cross-connection
row-lock semantics — SQLite tests must never stand in for that proof.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import socket
import subprocess
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.db import (
    AuditEventRow,
    DeviceLeaseRow,
    DeviceRow,
    MobileActionCommitRow,
    MobileTaskRow,
)
from cloudctl_api.mobile_actions import canonical_steps, steps_action_identity
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from sqlalchemy import select
from test_platform_tasks import (
    PROBE,
    _enroll,
    bind,
    create_account,
    create_direct_device,
    identity,
)
from test_xianyu_maintenance import _create_steps_task, delist_steps, polish_steps

POSTGRES_ENV = {**os.environ, "LC_ALL": "C", "LANG": "C", "LANGUAGE": "C"}

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def api() -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(Settings(env="test", repository_mode="memory", dev_auth_bypass=True))
    await app.state.database.create_schema()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


@pytest.fixture(scope="module")
def isolated_postgres(tmp_path_factory):
    """Never use DATABASE_URL: start our own disposable cluster on a free port."""
    if not all(shutil.which(tool) for tool in ("initdb", "pg_ctl", "createdb")):
        pytest.skip("local PostgreSQL binaries unavailable")
    root = tmp_path_factory.mktemp("a11-postgres")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
        ["initdb", "-D", str(root / "data"), "-A", "trust", "-U", "a11test"],  # noqa: S607
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
def pg_url(isolated_postgres):
    name = "a11_" + uuid.uuid4().hex
    subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
        ["createdb", "-h", "127.0.0.1", "-p", str(isolated_postgres), "-U", "a11test", name],  # noqa: S607
        check=True,
        capture_output=True,
        env=POSTGRES_ENV,
    )
    return f"postgresql+asyncpg://a11test@127.0.0.1:{isolated_postgres}/{name}"


@asynccontextmanager
async def api_process(pg_url: str) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    """One independent API process (own engine/connection pool) on the cluster."""
    app = create_app(
        Settings(
            env="test",
            repository_mode="postgresql",
            database_url=pg_url,
            dev_auth_bypass=True,
        )
    )
    await app.state.database.create_schema()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def registry_version() -> str:
    from cloudctl_api.mobile_service import COMMAND_REGISTRY_VERSION

    return COMMAND_REGISTRY_VERSION


def payload_identity(steps: list[dict[str, Any]]) -> str:
    """fleet-identity/v1 §7 payloadIdentity over the real steps (no header)."""
    real = [step for step in steps if step.get("action")]
    return hashlib.sha256(canonical_steps(real).encode()).hexdigest()


async def claim(client: httpx.AsyncClient, auth: dict[str, str]) -> httpx.Response:
    return await client.post("/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60})


async def release(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    task_id: str,
    lease_id: str,
    *,
    reason: str = "ACCESSIBILITY_NOT_ACTIVE",
) -> httpx.Response:
    return await client.post(
        f"/companion/v2/tasks/{task_id}/release",
        headers=auth,
        json={"leaseId": lease_id, "reason": reason},
    )


async def patch_task(app: FastAPI, task_id: str, mutate: Callable[[MobileTaskRow], None]) -> None:
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        mutate(row)


def expire_lease(row: MobileTaskRow) -> None:
    row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)


async def frozen_steps_flow(
    client: httpx.AsyncClient, name: str
) -> tuple[str, str, dict[str, str], dict[str, Any]]:
    """Create + claim + release a frozen-steps task; ready for re-claim."""
    device = await create_direct_device(client, f"a11-{name}")
    created = await _create_steps_task(client, device, polish_steps(), f"a11-{name}-{uuid.uuid4()}")
    assert created.status_code == 201, created.text
    task_id = created.json()["taskId"]
    auth = await _enroll(client, device, f"a11-{name}-instance")
    first = await claim(client, auth)
    assert first.status_code == 200, first.text
    body = first.json()
    released = await release(client, auth, task_id, body["leaseId"])
    assert released.status_code == 200, released.text
    return task_id, device, auth, body


# ---------------------------------------------------------------------------
# §7 frozen-steps claim → release → reclaim
# ---------------------------------------------------------------------------


async def test_frozen_steps_claim_release_reclaim(api):
    """合法未提交固定 steps 可安全重领（任务卡验收 1）。"""
    client, app = api
    task_id, device, auth, first = await frozen_steps_flow(client, "reclaim")

    second = await claim(client, auth)
    assert second.status_code == 200, second.text
    reclaimed = second.json()
    assert reclaimed["taskId"] == task_id
    assert reclaimed["attempt"] == 2
    assert reclaimed["leaseId"] != first["leaseId"]

    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        metadata = row.steps[0]
        stored_real_steps = [step for step in row.steps if step.get("action")]
        assert metadata["payloadIdentity"] == payload_identity(stored_real_steps)
        assert metadata["payloadIdentity"] == payload_identity(polish_steps())
        assert metadata["commandRegistryVersion"] == registry_version()
        assert row.recipe_pin is None
        live_leases = list(
            await session.scalars(
                select(DeviceLeaseRow).where(
                    DeviceLeaseRow.device_id == device,
                    DeviceLeaseRow.canceled_at.is_(None),
                )
            )
        )
        assert [lease.lease_id for lease in live_leases] == [row.lease_id]
        audits = list(
            await session.scalars(
                select(AuditEventRow).where(
                    AuditEventRow.action == "recipe.task.pinned",
                    AuditEventRow.resource_id == task_id,
                )
            )
        )
        assert len(audits) == 1


async def test_release_requires_preflight_before_first_heartbeat(api):
    """§8/P09-19: 首心跳后不可再释放回 QUEUED。"""
    client, _ = api
    device = await create_direct_device(client, "a11-release-guard")
    created = await _create_steps_task(
        client, device, polish_steps(), f"a11-relguard-{uuid.uuid4()}"
    )
    task_id = created.json()["taskId"]
    auth = await _enroll(client, device, "a11-release-guard-instance")
    first = await claim(client, auth)
    assert first.status_code == 200, first.text
    heartbeat = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": first.json()["leaseId"], "currentStep": 0},
    )
    assert heartbeat.status_code == 200, heartbeat.text
    response = await release(client, auth, task_id, first.json()["leaseId"])
    assert response.status_code == 409
    assert "only a claimed task in PREFLIGHT" in response.json()["detail"]


async def test_frozen_steps_reclaim_rejects_payload_mutation(api):
    """§7: 重领校验不可变 payloadIdentity，篡改 steps → 409。"""
    client, app = api
    task_id, _, auth, _ = await frozen_steps_flow(client, "mutated")

    def mutate(row: MobileTaskRow) -> None:
        steps = [dict(step) for step in row.steps]
        for step in steps:
            if step.get("stepId") == "open-profile":
                step["locatorRef"] = "xianyu_somewhere_else"
        row.steps = steps

    await patch_task(app, task_id, mutate)
    response = await claim(client, auth)
    assert response.status_code == 409
    assert "payload identity changed" in response.json()["detail"]


async def test_frozen_steps_reclaim_rejects_registry_version_change(api):
    """§7: 重领校验 commandRegistryVersion，版本漂移 → 409。"""
    client, app = api
    task_id, _, auth, _ = await frozen_steps_flow(client, "registry")

    def mutate(row: MobileTaskRow) -> None:
        metadata = dict(row.steps[0])
        metadata["commandRegistryVersion"] = "steps-registry/19990101.1"
        row.steps = [metadata, *row.steps[1:]]

    await patch_task(app, task_id, mutate)
    response = await claim(client, auth)
    assert response.status_code == 409
    assert "command registry" in response.json()["detail"]


async def test_frozen_steps_reclaim_without_frozen_identity_rejected(api):
    """§7 fail-closed: 领取过但从未冻结身份（pre-A11 行）→ 409，不得放行。"""
    client, app = api
    task_id, _, auth, _ = await frozen_steps_flow(client, "unfrozen")

    def mutate(row: MobileTaskRow) -> None:
        metadata = dict(row.steps[0])
        metadata.pop("payloadIdentity", None)
        metadata.pop("commandRegistryVersion", None)
        row.steps = [metadata, *row.steps[1:]]

    await patch_task(app, task_id, mutate)
    response = await claim(client, auth)
    assert response.status_code == 409
    assert "no persisted payload identity" in response.json()["detail"]


async def test_legacy_recipe_task_without_pin_still_rejected(api):
    """任务卡验收 2：legacy 无 pin 的 Recipe 任务（注册表外 commandType）仍拒绝。"""
    client, app = api
    device = await create_direct_device(client, "a11-legacy")
    account = await create_account(client, "a11-legacy-account")
    await bind(client, account, device)
    created = await client.post(
        "/api/v1/platform-tasks",
        headers={**identity(), "Idempotency-Key": f"a11-legacy-{uuid.uuid4()}"},
        json={"deviceId": device, "accountId": account, **PROBE},
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["items"][0]["taskId"]
    auth = await _enroll(client, device, "a11-legacy-instance")
    first = await claim(client, auth)
    assert first.status_code == 200, first.text
    assert first.json()["command"]["recipe"] is not None

    def mutate(row: MobileTaskRow) -> None:
        row.recipe_pin = None
        expire_lease(row)

    await patch_task(app, task_id, mutate)
    response = await claim(client, auth)
    assert response.status_code == 409
    assert "no persisted recipe pin" in response.json()["detail"]


# ---------------------------------------------------------------------------
# §8 post-commit recovery: 提交后断网/ACK 丢失不触发再次提交
# ---------------------------------------------------------------------------


async def test_committed_steps_task_not_reexecuted_after_ack_loss(api):
    """任务卡验收 5：gated 点击已写台账后断网，回收不得把任务当新任务再执行。"""
    client, app = api
    device = await create_direct_device(client, "a11-ackloss")
    created = await _create_steps_task(
        client, device, delist_steps(0), f"a11-ackloss-{uuid.uuid4()}"
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["taskId"]
    auth = await _enroll(client, device, "a11-ackloss-instance")
    first = await claim(client, auth)
    lease_id = first.json()["leaseId"]
    started = await client.post(
        f"/companion/v2/tasks/{task_id}/heartbeat",
        headers=auth,
        json={"leaseId": lease_id, "currentStep": 2},
    )
    assert started.status_code == 200, started.text
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        frozen = steps_action_identity(row)
    intent = await client.post(
        f"/companion/v2/tasks/{task_id}/actions/intent",
        headers=auth,
        json={
            "leaseId": lease_id,
            "actionId": frozen["action_id"],
            "actionKey": frozen["action_key"],
            "parameterHash": frozen["parameter_hash"],
            "beforeEvidence": "evidence://a11-before",
        },
    )
    assert intent.status_code == 201, intent.text

    # Network drops here: the lease lapses with no outcome/finish ACK.
    await patch_task(app, task_id, expire_lease)
    response = await claim(client, auth)
    assert response.status_code == 204
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row.business_state == "RECONCILING"
        assert row.attempt == 1
        ledger = list(
            await session.scalars(
                select(MobileActionCommitRow).where(MobileActionCommitRow.task_id == task_id)
            )
        )
        assert [item.status for item in ledger] == ["INTENT"]

    # Drift hardening: even if the runner state is corrupted back to QUEUED,
    # the ledger row must keep the committed task from being re-dispatched.
    def drift(row: MobileTaskRow) -> None:
        row.status = "QUEUED"
        row.business_state = "QUEUED"
        row.lease_id = None
        expire_lease(row)

    await patch_task(app, task_id, drift)
    response = await claim(client, auth)
    assert response.status_code == 204
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row.business_state == "RECONCILING"
        assert row.attempt == 1
        assert row.status == "QUEUED"


async def test_queued_task_with_legacy_commit_intent_not_reclaimed(api):
    """过期回收先查意图：遗留 commitIntent 未决 → 挂 RECONCILING，不重新派发。"""
    client, app = api
    task_id, _, auth, _ = await frozen_steps_flow(client, "commit-intent")

    def mutate(row: MobileTaskRow) -> None:
        row.command_payload = {"commitIntent": {"productId": "a11-product"}}

    await patch_task(app, task_id, mutate)
    response = await claim(client, auth)
    assert response.status_code == 204
    async with app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row.business_state == "RECONCILING"
        assert row.attempt == 1


# ---------------------------------------------------------------------------
# PostgreSQL concurrency proofs (真实 PG；SQLite 不得替代)
# ---------------------------------------------------------------------------


async def test_postgres_frozen_steps_release_and_reclaim(pg_url):
    """§7/§8 完整释放-重领周期在真实 PostgreSQL 行锁下成立。"""
    async with api_process(pg_url) as (client, _):
        device = await create_direct_device(client, "a11-pg-reclaim")
        created = await _create_steps_task(
            client, device, polish_steps(), f"a11-pg-reclaim-{uuid.uuid4()}"
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["taskId"]
        auth = await _enroll(client, device, "a11-pg-reclaim-instance")
        first = await claim(client, auth)
        assert first.status_code == 200, first.text
        released = await release(client, auth, task_id, first.json()["leaseId"])
        assert released.status_code == 200, released.text
        second = await claim(client, auth)
        assert second.status_code == 200, second.text
        assert second.json()["attempt"] == 2
        assert second.json()["taskId"] == task_id


async def test_postgres_same_device_two_processes_single_holder(pg_url):
    """任务卡验收 3：两个 API 进程同设备并发 claim，至多一位有效持有者。"""
    async with (
        api_process(pg_url) as (client1, app1),
        api_process(pg_url) as (
            client2,
            _,
        ),
    ):
        device = await create_direct_device(client1, "a11-pg-race")
        created = await _create_steps_task(
            client1, device, polish_steps(), f"a11-pg-race-{uuid.uuid4()}"
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["taskId"]
        auth = await _enroll(client1, device, "a11-pg-race-instance")
        responses = await asyncio.gather(claim(client1, auth), claim(client2, auth))
        assert sorted(response.status_code for response in responses) == [200, 204]
        winner = next(response for response in responses if response.status_code == 200)
        assert winner.json()["taskId"] == task_id
        async with app1.state.database.unit_of_work() as session:
            active = list(
                await session.scalars(
                    select(MobileTaskRow).where(
                        MobileTaskRow.device_id == device,
                        MobileTaskRow.status.in_(("CLAIMED", "RUNNING")),
                    )
                )
            )
            assert len(active) == 1
            assert active[0].attempt == 1
            assert active[0].lease_id == winner.json()["leaseId"]
            live_leases = list(
                await session.scalars(
                    select(DeviceLeaseRow).where(
                        DeviceLeaseRow.device_id == device,
                        DeviceLeaseRow.canceled_at.is_(None),
                    )
                )
            )
            assert len(live_leases) == 1


async def test_postgres_different_devices_do_not_wait_on_global_lock(pg_url):
    """任务卡验收 4：异设备并行——设备 A 行锁被持有时，设备 B 照常领取。"""
    async with (
        api_process(pg_url) as (client1, app1),
        api_process(pg_url) as (
            client2,
            _,
        ),
    ):
        device_a = await create_direct_device(client1, "a11-pg-lock-a")
        device_b = await create_direct_device(client1, "a11-pg-lock-b")
        created = await _create_steps_task(
            client1, device_b, polish_steps(), f"a11-pg-lock-b-{uuid.uuid4()}"
        )
        assert created.status_code == 201, created.text
        task_b = created.json()["taskId"]
        auth_b = await _enroll(client1, device_b, "a11-pg-lock-b-instance")
        async with app1.state.database.session_factory() as holder:
            locked = await holder.get(DeviceRow, device_a, with_for_update=True)
            assert locked is not None  # device A row lock held on connection 1
            response = await asyncio.wait_for(claim(client2, auth_b), timeout=5.0)
            assert response.status_code == 200, response.text
            assert response.json()["taskId"] == task_b
