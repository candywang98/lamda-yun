"""PG-LOCK-ORDER: real PostgreSQL same-device lock-order regressions.

The immutable red characterization is in commit 2140f6954ed51c47c08949b6935e27ec722b7d61.
Only the scheduling of real production row locks is instrumented; SQL, request
authentication, task/lease validation, and transaction handling stay unchanged.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import uuid
from collections.abc import AsyncIterator, Iterator
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app, mobile_service
from cloudctl_api.db import Database, DeviceLeaseRow, DeviceRow, MobileTaskRow
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import AsyncAdaptedQueuePool
from test_fleet_live_session import ack, establish, take_control
from test_mobile_task_api import create_direct_device, enroll, identity

SOURCE_SHA = "7d58f6b28158292722c7d037998163f5fcbfca89"
PROBE_SECONDS = 20
DRAIN_SECONDS = 5
ROLE: ContextVar[str | None] = ContextVar("mobile_lock_order_role", default=None)
PHASES = ("PREFLIGHT", "RUNNING")
OPERATIONS = ("finish", "heartbeat")


def pool_checked_out(database: Database) -> int:
    pool = database.engine.pool
    assert isinstance(pool, AsyncAdaptedQueuePool)
    return pool.checkedout()


def pg_command(argv: list[str]) -> subprocess.CompletedProcess[str]:
    # No ambient PG connection/service/options variables or application settings.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PG", "CLOUDCTL_")) and key != "DATABASE_URL"
    }
    env.update(LC_ALL="C", LANG="C", LANGUAGE="C")
    return subprocess.run(  # noqa: S603 - resolved tools, fixed args, test-owned paths only
        argv, check=True, capture_output=True, text=True, timeout=30, env=env
    )


@dataclass(frozen=True)
class OwnedPostgres:
    root: Path
    port: int
    createdb: str


@pytest.fixture(scope="module")
def owned_postgres(tmp_path_factory: pytest.TempPathFactory) -> Iterator[OwnedPostgres]:
    tools = {tool: shutil.which(tool) for tool in ("initdb", "pg_ctl", "createdb")}
    assert all(tools.values()), f"PostgreSQL tools required; no skip/fallback: {tools}"
    initdb, pg_ctl, createdb = (str(tools[name]) for name in ("initdb", "pg_ctl", "createdb"))
    root = tmp_path_factory.mktemp("mobile-lock-order-pg").resolve()
    data = root / "data"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    try:
        pg_command([initdb, "-D", str(data), "-A", "trust", "-U", "lockorder"])
        pg_command(
            [
                pg_ctl,
                "-D",
                str(data),
                "-l",
                str(root / "server.log"),
                "-o",
                f"-h 127.0.0.1 -p {port} -c unix_socket_directories='' "
                "-c statement_timeout=10000 -c log_error_verbosity=verbose",
                "-t",
                "10",
                "-w",
                "start",
            ]
        )
        yield OwnedPostgres(root, port, createdb)
    finally:
        if (data / "postmaster.pid").exists():
            pg_command([pg_ctl, "-D", str(data), "-m", "fast", "-t", "10", "-w", "stop"])
        assert not (data / "postmaster.pid").exists(), "test-owned PostgreSQL still running"
        print(f"\nPG_CLUSTER_STOPPED={root}")


@pytest.fixture
def owned_pg_url(owned_postgres: OwnedPostgres) -> str:
    name = "lockorder_" + uuid.uuid4().hex
    pg_command(
        [
            owned_postgres.createdb,
            "-h",
            "127.0.0.1",
            "-p",
            str(owned_postgres.port),
            "-U",
            "lockorder",
            name,
        ]
    )
    return f"postgresql+asyncpg://lockorder@127.0.0.1:{owned_postgres.port}/{name}"


@pytest.fixture
async def pg_api(
    owned_pg_url: str, owned_postgres: OwnedPostgres, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    for key in tuple(os.environ):
        if key.startswith("CLOUDCTL_") or key == "DATABASE_URL":
            monkeypatch.delenv(key)
    app = create_app(
        Settings(
            env="test",
            repository_mode="postgresql",
            database_url=owned_pg_url,
            dev_auth_bypass=True,
            object_store_mode="memory",
            im_classifier_enabled=False,
        )
    )
    database: Database = app.state.database
    try:
        async with database.engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT current_setting('data_directory') AS data_directory, "
                            "current_setting('server_version') AS version, "
                            "current_setting('deadlock_timeout') AS deadlock_timeout, "
                            "current_setting('statement_timeout') AS statement_timeout, "
                            "current_setting('lock_timeout') AS lock_timeout, "
                            "current_setting('transaction_isolation') AS isolation"
                        )
                    )
                )
                .mappings()
                .one()
            )
            assert row["data_directory"] == str(owned_postgres.root / "data")
            assert row["deadlock_timeout"] == "1s"
            assert row["lock_timeout"] == "0"
            assert row["statement_timeout"] == "10s"
            app.state.lock_order_pg = dict(row)
        await database.create_schema()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                yield client, app
    finally:
        # Also covers schema/lifespan entry failure, before lifespan owns disposal.
        await database.dispose()
        assert pool_checked_out(database) == 0


@dataclass(frozen=True)
class ActiveTask:
    device_id: str
    task_id: str
    lease_id: str
    auth: dict[str, str]


async def request_operation(
    client: httpx.AsyncClient, active: ActiveTask, operation: str
) -> httpx.Response:
    if operation == "claim":
        return await client.post(
            "/companion/v2/tasks/claim", headers=active.auth, json={"leaseSeconds": 60}
        )
    if operation == "heartbeat":
        suffix = "heartbeat"
        body = {"leaseId": active.lease_id, "currentStep": 1, "leaseSeconds": 60}
    else:
        assert operation == "finish"
        suffix = "complete"
        body = {"leaseId": active.lease_id, "result": {"lockOrderProbe": True}}
    return await client.post(
        f"/companion/v2/tasks/{active.task_id}/{suffix}", headers=active.auth, json=body
    )


async def prepare_active(client: httpx.AsyncClient, phase: str) -> ActiveTask:
    device_id = await create_direct_device(client)
    token = await enroll(client, device_id)
    created = await client.post(
        "/api/v1/mobile/tasks",
        headers={**identity(), "Idempotency-Key": str(uuid.uuid4())},
        json={
            "deviceId": device_id,
            "targetPackage": "com.company.cloudctl.companion",
            "totalTimeoutMs": 30_000,
            "steps": [
                {
                    "stepId": f"local-log-{index}",
                    "action": "run.log",
                    "level": "INFO",
                    "messageCode": "PG_LOCK_ORDER_PROBE",
                    "timeoutMs": 1_000,
                }
                for index in range(2)
            ],
        },
    )
    assert created.status_code == 201, created.text
    auth = {"Authorization": f"Bearer {token}"}
    claimed = await client.post(
        "/companion/v2/tasks/claim", headers=auth, json={"leaseSeconds": 60}
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["taskId"] == created.json()["taskId"]
    active = ActiveTask(device_id, created.json()["taskId"], claimed.json()["leaseId"], auth)
    if phase == "RUNNING":
        heartbeat = await client.post(
            f"/companion/v2/tasks/{active.task_id}/heartbeat",
            headers=active.auth,
            json={"leaseId": active.lease_id, "currentStep": 0, "leaseSeconds": 60},
        )
        assert heartbeat.status_code == 200, heartbeat.text
    else:
        assert phase == "PREFLIGHT"
    return active


async def durable_state(database: Database, active: ActiveTask) -> dict[str, Any]:
    async with database.unit_of_work() as session:
        tasks = list(
            await session.scalars(
                select(MobileTaskRow).where(MobileTaskRow.device_id == active.device_id)
            )
        )
        leases = list(
            await session.scalars(
                select(DeviceLeaseRow).where(DeviceLeaseRow.device_id == active.device_id)
            )
        )
        assert len(tasks) == len(leases) == 1
        task, lease = tasks[0], leases[0]
        device = await session.get(DeviceRow, active.device_id)
        assert device is not None
        assert task.id == active.task_id
        assert task.lease_id == lease.lease_id == active.lease_id
        assert task.tenant_id == lease.tenant_id == device.tenant_id
        assert lease.owner_workflow_id == f"auto/{task.id}"
        assert lease.owner_type == "AUTO"
        assert device.fencing_counter == lease.fencing_token
        assert task.attempt == 1

        def timestamp(value: datetime | None) -> str | None:
            return value.isoformat() if value is not None else None

        return {
            "task_id": task.id,
            "device_id": device.id,
            "lease_id": lease.lease_id,
            "status": task.status,
            "business_state": task.business_state,
            "current_step": task.current_step,
            "result": task.result,
            "error_code": task.error_code,
            "detail": task.detail,
            "completed_at": timestamp(task.completed_at),
            "task_expires_at": timestamp(task.lease_expires_at),
            "lease_expires_at": timestamp(lease.expires_at),
            "lease_canceled_at": timestamp(lease.canceled_at),
            "attempt": task.attempt,
            "fencing_token": lease.fencing_token,
        }


async def assert_database_idle(database: Database) -> None:
    async with database.engine.connect() as connection:
        unfinished = list(
            (
                await connection.execute(
                    text(
                        "SELECT pid, state, wait_event_type FROM pg_stat_activity "
                        "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                        "AND (xact_start IS NOT NULL OR wait_event_type = 'Lock')"
                    )
                )
            ).mappings()
        )
    assert unfinished == [], f"test-owned database has unfinished transactions: {unfinished}"


def assert_initial(state: dict[str, Any], phase: str) -> None:
    assert state["business_state"] == phase
    assert state["status"] == ("CLAIMED" if phase == "PREFLIGHT" else "RUNNING")
    assert state["result"] == {}
    assert state["completed_at"] is state["lease_canceled_at"] is None
    assert state["task_expires_at"] == state["lease_expires_at"]
    assert datetime.fromisoformat(state["task_expires_at"]) > datetime.now(UTC)


def assert_updated(state: dict[str, Any], operation: str) -> None:
    assert state["error_code"] is state["detail"] is None
    if operation == "finish":
        assert state["status"] == state["business_state"] == "SUCCEEDED"
        assert state["result"] == {"lockOrderProbe": True}
        assert state["completed_at"] == state["lease_canceled_at"]
        assert state["completed_at"] is not None
        assert state["task_expires_at"] is None
    else:
        assert state["status"] == state["business_state"] == "RUNNING"
        assert state["current_step"] == 1
        assert state["result"] == {}
        assert state["completed_at"] is state["lease_canceled_at"] is None
        assert state["task_expires_at"] == state["lease_expires_at"]
        assert datetime.fromisoformat(state["task_expires_at"]) > datetime.now(UTC)


@dataclass
class LockSchedule:
    runner_holds_task: asyncio.Event = field(default_factory=asyncio.Event)
    claim_requests_task: asyncio.Event = field(default_factory=asyncio.Event)
    claim_requests_lease: asyncio.Event = field(default_factory=asyncio.Event)
    release_runner: asyncio.Event = field(default_factory=asyncio.Event)
    acquired: dict[str, dict[str, int]] = field(default_factory=dict)
    locks_at_claim_task_request: dict[str, dict[str, int]] = field(default_factory=dict)
    sql: list[dict[str, str]] = field(default_factory=list)
    workers: list[asyncio.Task[dict[str, Any]]] = field(default_factory=list)

    def trace_sql(self, _conn, _cursor, statement, _parameters, _context, _many) -> None:
        role = ROLE.get()
        normalized = " ".join(statement.split())
        if role is None or "FOR UPDATE" not in normalized:
            return
        for table in ("device", "device_lease", "mobile_task"):
            if f"FROM {table} " not in normalized:
                continue
            self.sql.append({"operation": role, "table": table, "sql": normalized})
            if role == "claim" and table == "mobile_task" and not self.claim_requests_task.is_set():
                self.locks_at_claim_task_request = {
                    owner: dict(locks) for owner, locks in self.acquired.items()
                }
                self.claim_requests_task.set()
            if role == "claim" and table == "device_lease":
                self.claim_requests_lease.set()

    def install(self, patch: pytest.MonkeyPatch, database: Database, active: ActiveTask) -> None:
        original_get = AsyncSession.get

        async def observed_get(session, entity, ident, **kwargs):
            row = await original_get(session, entity, ident, **kwargs)
            role = ROLE.get()
            if (
                session.bind is database.engine
                and role is not None
                and kwargs.get("with_for_update") is True
                and entity in (DeviceRow, DeviceLeaseRow, MobileTaskRow)
                and row is not None
            ):
                table = entity.__tablename__
                pid = int(await session.scalar(text("SELECT pg_backend_pid()")))
                self.acquired.setdefault(role, {})[table] = pid
                if role != "claim" and entity is MobileTaskRow:
                    assert ident == active.task_id
                    assert row.lease_id == active.lease_id
                    self.runner_holds_task.set()
                    await self.release_runner.wait()
            return row

        patch.setattr(AsyncSession, "get", observed_get)


def exception_details(error: Exception) -> dict[str, Any]:
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    chain: list[dict[str, Any]] = []
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        sqlstate = getattr(current, "sqlstate", None)
        if sqlstate is not None:
            chain.append(
                {
                    "type": type(current).__name__,
                    "sqlstate": sqlstate,
                    "message": str(current),
                    "detail": getattr(current, "detail", None),
                }
            )
        for name in ("orig", "__cause__", "__context__"):
            nested = getattr(current, name, None)
            if isinstance(nested, BaseException):
                pending.append(nested)
        pending.extend(getattr(current, "exceptions", ()))
    return {
        "exception": type(error).__name__,
        "sqlstates": sorted({item["sqlstate"] for item in chain}),
        "database_errors": chain,
        "message": str(error) if not chain else None,
    }


async def operation_outcome(
    client: httpx.AsyncClient, active: ActiveTask, operation: str
) -> dict[str, Any]:
    token = ROLE.set(operation)
    try:
        response = await request_operation(client, active, operation)
        return {
            "operation": operation,
            "http_status": response.status_code,
            "body": response.json() if response.content else None,
            "sqlstates": [],
        }
    except Exception as exc:
        return {"operation": operation, **exception_details(exc)}
    finally:
        ROLE.reset(token)


async def interleave(
    client: httpx.AsyncClient,
    database: Database,
    active: ActiveTask,
    operation: str,
    schedule: LockSchedule,
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, Any]]:
    with monkeypatch.context() as patch:
        schedule.install(patch, database, active)
        event.listen(database.engine.sync_engine, "before_cursor_execute", schedule.trace_sql)
        try:
            async with asyncio.timeout(PROBE_SECONDS):
                runner = asyncio.create_task(
                    operation_outcome(client, active, operation), name=f"lock-order-{operation}"
                )
                schedule.workers.append(runner)
                await schedule.runner_holds_task.wait()
                claimant = asyncio.create_task(
                    operation_outcome(client, active, "claim"), name="lock-order-claim"
                )
                schedule.workers.append(claimant)
                # The baseline reaches the task request while holding the lease.
                # Also allow a later approved fix to acquire either common order;
                # never require it to retain the baseline's opposite first locks.
                if "device_lease" in schedule.acquired[operation]:
                    await schedule.claim_requests_lease.wait()
                else:
                    await schedule.claim_requests_task.wait()
                schedule.release_runner.set()
                return list(await asyncio.gather(claimant, runner))
        finally:
            schedule.release_runner.set()
            for worker in schedule.workers:
                if not worker.done():
                    worker.cancel()
            try:
                async with asyncio.timeout(DRAIN_SECONDS):
                    await asyncio.gather(*schedule.workers, return_exceptions=True)
                assert all(worker.done() for worker in schedule.workers)
                assert pool_checked_out(database) == 0
            finally:
                event.remove(
                    database.engine.sync_engine, "before_cursor_execute", schedule.trace_sql
                )


async def probe(
    pg_api: tuple[httpx.AsyncClient, FastAPI],
    operation: str,
    phase: str,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    client, app = pg_api
    database: Database = app.state.database
    active = await prepare_active(client, phase)
    before = await durable_state(database, active)
    assert_initial(before, phase)
    schedule = LockSchedule()
    outcomes = await interleave(client, database, active, operation, schedule, monkeypatch)
    after = await durable_state(database, active)
    await assert_database_idle(database)
    report = {
        "characterization_baseline_sha": SOURCE_SHA,
        "runtime_service_file": mobile_service.__file__,
        "postgres": app.state.lock_order_pg,
        "operation": operation,
        "phase": phase,
        "acquired_locks": schedule.acquired,
        "locks_at_claim_task_request": schedule.locks_at_claim_task_request,
        "lock_sql": schedule.sql,
        "outcomes": outcomes,
        "before": before,
        "after": after,
        "workers_drained": all(worker.done() for worker in schedule.workers),
        "pool_checked_out": pool_checked_out(database),
        "unfinished_transactions": 0,
    }
    print("\nLOCK_ORDER_PROBE=" + json.dumps(report, sort_keys=True))
    runner = next(outcome for outcome in outcomes if outcome["operation"] == operation)
    if runner.get("http_status") == 200:
        assert_updated(after, operation)
    elif runner.get("exception"):
        assert after == before, "aborted runner must roll back completely"
    return report


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("phase", PHASES)
async def test_sequential_claim_and_update_preserve_valid_state(pg_api, operation, phase):
    client, app = pg_api
    active = await prepare_active(client, phase)
    assert_initial(await durable_state(app.state.database, active), phase)
    claimed = await request_operation(client, active, "claim")
    assert claimed.status_code == 204, claimed.text
    updated = await request_operation(client, active, operation)
    assert updated.status_code == 200, updated.text
    assert_updated(await durable_state(app.state.database, active), operation)


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("phase", PHASES)
async def test_claim_and_update_should_not_deadlock(pg_api, monkeypatch, operation, phase):
    """Both operations complete without deadlock, retry, or altered validation."""
    report = await probe(pg_api, operation, phase, monkeypatch)
    for outcome in report["outcomes"]:
        expected_status = 204 if outcome["operation"] == "claim" else 200
        assert outcome.get("http_status") == expected_status, outcome
    assert_updated(report["after"], operation)


@pytest.mark.parametrize("phase", PHASES)
async def test_remote_lease_guard_preserves_active_task_precedence(pg_api, phase):
    client, app = pg_api
    active = await prepare_active(client, phase)
    opened = await establish(client, active.device_id, "INTERACTIVE_REMOTE")
    assert opened.status_code == 201, opened.text
    sid, token = opened.json()["sessionId"], opened.json()["sessionToken"]
    acknowledged = await ack(client, active.auth, sid, granted=True)
    assert acknowledged.status_code == 200, acknowledged.text
    controlled = await take_control(client, sid, token)
    assert controlled.status_code == 200, controlled.text
    assert controlled.json()["state"] == "REMOTE"

    async def snapshot() -> dict[str, Any]:
        async with app.state.database.unit_of_work() as session:
            task = await session.get(MobileTaskRow, active.task_id)
            lease = await session.get(DeviceLeaseRow, active.device_id)
            device = await session.get(DeviceRow, active.device_id)
            assert task is not None and lease is not None and device is not None
            assert task.lease_id == active.lease_id
            assert task.lease_expires_at is not None
            assert task.lease_expires_at > datetime.now(UTC)
            assert lease.owner_type == "REMOTE"
            assert lease.owner_workflow_id == f"live/{sid}"
            assert lease.expires_at > datetime.now(UTC)
            assert lease.canceled_at is None
            assert lease.fencing_token == device.fencing_counter
            return {
                "task_status": task.status,
                "business_state": task.business_state,
                "task_lease": task.lease_id,
                "task_expiry": task.lease_expires_at,
                "attempt": task.attempt,
                "remote_lease": lease.lease_id,
                "remote_expiry": lease.expires_at,
                "fencing_token": lease.fencing_token,
            }

    before = await snapshot()
    claimed = await request_operation(client, active, "claim")
    if phase == "PREFLIGHT":
        assert before["task_status"] == "CLAIMED"
        assert before["business_state"] == "PREFLIGHT"
        assert claimed.status_code == 409, claimed.text
        assert "device write lease is held by remote control" in claimed.text
    else:
        assert before["task_status"] == "RUNNING"
        assert before["business_state"] == "PAUSED_WAITING_USER"
        assert claimed.status_code == 204, claimed.text
    assert await snapshot() == before
    await assert_database_idle(app.state.database)


async def test_cancelled_probe_drains_workers_before_database_disposal(pg_api, monkeypatch):
    client, app = pg_api
    database: Database = app.state.database
    active = await prepare_active(client, "PREFLIGHT")
    before = await durable_state(database, active)
    schedule = LockSchedule()
    task = asyncio.create_task(
        interleave(client, database, active, "heartbeat", schedule, monkeypatch)
    )
    try:
        async with asyncio.timeout(PROBE_SECONDS):
            await schedule.claim_requests_task.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    finally:
        schedule.release_runner.set()
        task.cancel()
        async with asyncio.timeout(DRAIN_SECONDS):
            await asyncio.gather(task, return_exceptions=True)
    assert len(schedule.workers) == 2
    assert all(worker.done() for worker in schedule.workers)
    assert pool_checked_out(database) == 0
    assert await durable_state(database, active) == before
    await assert_database_idle(database)
    print("\nCANCELLED_PROBE_DRAINED=2; pool_checked_out=0; unfinished_transactions=0")
