"""Desired control-lock regressions; historical expectations live in artifacts.

Only disposable PostgreSQL is supported. Every state is created through ASGI
requests, including Companion bearer authentication and live authorization.
The scheduler pauses the first request after its *first* actual row lock, not
after a prescribed table. A future common-order fix can therefore serialize
the requests without preserving either historical inversion.
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
from contextlib import AsyncExitStack
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.db import DeviceLeaseRow, MobileTaskRow
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession

ROLE: ContextVar[str | None] = ContextVar("control_lock_request", default=None)
TENANT = "00000000-0000-7000-8000-000000000111"
OPERATOR = "00000000-0000-7000-8000-000000000222"
SCENARIOS = ("queued_cancel", "live_take_control")


def operator_headers() -> dict[str, str]:
    return {
        "X-Tenant-Id": TENANT,
        "X-User-Id": OPERATOR,
        "X-Roles": "device_operator",
        "X-MFA": "true",
    }


@dataclass
class OwnedPostgres:
    root: Path
    tools: dict[str, str]
    port: int
    environment: dict[str, str]

    def run(self, tool: str, *arguments: str) -> None:
        result = subprocess.run(  # noqa: S603 - discovered PG binaries, owned temp paths
            [self.tools[tool], *arguments],
            capture_output=True,
            text=True,
            env=self.environment,
            timeout=30,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                f"{tool} exited {result.returncode}: {result.stdout}\n{result.stderr}"
            )

    def stop(self) -> None:
        data = self.root / "data"
        if (data / "postmaster.pid").exists():
            self.run("pg_ctl", "-D", str(data), "-m", "immediate", "-w", "-t", "20", "stop")
        # Stopping must succeed before the test-owned data can be removed.
        shutil.rmtree(self.root)
        print(f"CONTROL_LOCK_CLUSTER_CLEANUP {self.root}: stopped and removed")


@pytest.fixture(scope="module")
def control_postgres(tmp_path_factory: pytest.TempPathFactory) -> Iterator[OwnedPostgres]:
    tools = {}
    for name in ("initdb", "pg_ctl", "createdb"):
        path = shutil.which(name)
        if path is None:
            pytest.fail(f"Control-lock tests require local PostgreSQL binary on PATH: {name}")
        tools[name] = path
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PG") and key not in {"DATABASE_URL", "CLOUDCTL_DATABASE_URL"}
    }
    environment.update(LC_ALL="C", LANG="C", LANGUAGE="C")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    cluster = OwnedPostgres(
        tmp_path_factory.mktemp("control-lock-owned-pg"), tools, port, environment
    )
    try:
        data = str(cluster.root / "data")
        cluster.run("initdb", "-D", data, "-A", "trust", "-U", "controltest")
        cluster.run(
            "pg_ctl",
            "-D",
            data,
            "-l",
            str(cluster.root / "server.log"),
            "-o",
            f"-h 127.0.0.1 -p {port} -c unix_socket_directories=''",
            "-w",
            "-t",
            "20",
            "start",
        )
        yield cluster
    finally:
        cluster.stop()


@dataclass
class Api:
    app: FastAPI
    client: httpx.AsyncClient


@pytest.fixture
async def control_apis(control_postgres: OwnedPostgres) -> AsyncIterator[tuple[Api, Api]]:
    name = "control_" + uuid.uuid4().hex
    control_postgres.run(
        "createdb",
        "--no-password",
        "-h",
        "127.0.0.1",
        "-p",
        str(control_postgres.port),
        "-U",
        "controltest",
        name,
    )
    url = f"postgresql+asyncpg://controltest@127.0.0.1:{control_postgres.port}/{name}"
    apis = []
    async with AsyncExitStack() as stack:
        for _ in range(2):
            app = create_app(
                Settings(
                    env="test",
                    repository_mode="postgresql",
                    database_url=url,
                    object_store_mode="memory",
                    dev_auth_bypass=True,
                )
            )
            # Also dispose when schema setup or lifespan entry raises.
            stack.push_async_callback(app.state.database.dispose)
            await app.state.database.create_schema()
            await stack.enter_async_context(app.router.lifespan_context(app))
            client = await stack.enter_async_context(
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                    base_url="http://test",
                )
            )
            apis.append(Api(app, client))
        yield apis[0], apis[1]
    print("CONTROL_LOCK_APIS_CLEANUP clients closed; lifespans exited; engines disposed")


async def post(
    api: Api,
    path: str,
    headers: dict[str, str],
    body: dict[str, Any] | None,
    expected: int = 200,
) -> dict[str, Any]:
    response = await api.client.post(path, headers=headers, json=body)
    assert response.status_code == expected, (path, response.status_code, response.text)
    return dict(response.json())


async def provision(api: Api) -> tuple[str, dict[str, str]]:
    device = await post(
        api,
        "/api/v1/mobile/devices",
        operator_headers(),
        {"logicalName": "control-lock-simulated", "androidVersion": "14", "companionVersion": "1"},
        201,
    )
    device_id = str(device["id"])
    enrollment = await post(
        api,
        "/api/v1/mobile/enrollments",
        operator_headers(),
        {"deviceId": device_id, "ttlSeconds": 600},
        201,
    )
    enrolled = await post(
        api,
        "/companion/v2/enroll",
        {},
        {
            "code": enrollment["code"],
            "appInstanceId": "control-lock-instance",
            "companionVersion": "1",
        },
        201,
    )
    return device_id, {"Authorization": f"Bearer {enrolled['bindingToken']}"}


async def create_read_task(api: Api, device: str) -> str:
    created = await post(
        api,
        "/api/v1/mobile/tasks",
        {**operator_headers(), "Idempotency-Key": uuid.uuid4().hex},
        {
            "deviceId": device,
            "targetPackage": "com.company.cloudctl.companion",
            "totalTimeoutMs": 60_000,
            "steps": [
                {
                    "stepId": "inspect",
                    "action": "ui.find",
                    "locatorRef": "screen.status",
                    "timeoutMs": 5_000,
                }
            ],
        },
        201,
    )
    return str(created["id"])


async def durable(api: Api, device: str) -> dict[str, Any]:
    async with api.app.state.database.unit_of_work() as session:
        tasks = list(
            await session.scalars(
                select(MobileTaskRow)
                .where(MobileTaskRow.device_id == device)
                .order_by(MobileTaskRow.created_at)
            )
        )
        lease = await session.get(DeviceLeaseRow, device)
        return {
            "tasks": [
                {
                    "id": row.id,
                    "status": row.status,
                    "businessState": row.business_state,
                    "leaseId": row.lease_id,
                    "leaseExpiresAt": row.lease_expires_at,
                    "attempt": row.attempt,
                    "result": row.result,
                    "errorCode": row.error_code,
                }
                for row in tasks
            ],
            "lease": None
            if lease is None
            else {
                "id": lease.lease_id,
                "owner": lease.owner_type,
                "workflow": lease.owner_workflow_id,
                "canceledAt": lease.canceled_at,
                "expiresAt": lease.expires_at,
            },
        }


@dataclass
class Request:
    api: Api
    role: str
    path: str
    headers: dict[str, str]
    body: dict[str, Any] | None

    async def send(self) -> httpx.Response:
        token = ROLE.set(self.role)
        try:
            return await self.api.client.post(self.path, headers=self.headers, json=self.body)
        finally:
            ROLE.reset(token)


@dataclass
class LockSchedule:
    first_role: str
    held: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    pids: dict[str, int] = field(default_factory=dict)
    trace: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    wait_edge: dict[str, Any] | None = None
    locks_before_release: list[dict[str, Any]] = field(default_factory=list)

    def install(self, monkeypatch: pytest.MonkeyPatch, apis: tuple[Api, Api]) -> None:
        original = AsyncSession.get

        async def get(session: AsyncSession, entity: Any, ident: Any, **kwargs: Any) -> Any:
            role = ROLE.get()
            locking = bool(kwargs.get("with_for_update"))
            row = await original(session, entity, ident, **kwargs)
            if role == self.first_role and locking and row is not None and not self.held.is_set():
                self.held.set()
                await self.release.wait()
            return row

        monkeypatch.setattr(AsyncSession, "get", get)
        for api in apis:
            engine = api.app.state.database.engine.sync_engine
            event.listen(engine, "before_cursor_execute", self.before)
            event.listen(engine, "after_cursor_execute", self.after)
            event.listen(engine, "handle_error", self.error)

    def uninstall(self, apis: tuple[Api, Api]) -> None:
        for api in apis:
            engine = api.app.state.database.engine.sync_engine
            event.remove(engine, "before_cursor_execute", self.before)
            event.remove(engine, "after_cursor_execute", self.after)
            event.remove(engine, "handle_error", self.error)

    def record(self, phase: str, statement: str, parameters: Any) -> None:
        role = ROLE.get()
        sql = " ".join(statement.split())
        if role is None or not (
            "FOR UPDATE" in sql or sql.startswith(("UPDATE mobile_task ", "UPDATE device_lease "))
        ):
            return
        if sql.startswith("SELECT ") and " FROM " in sql:
            sql = "SELECT ... FROM {}".format(sql.split(" FROM ", 1)[1])  # noqa: S608 - log only
        self.trace.append(
            {
                "role": role,
                "pid": self.pids.get(role),
                "phase": phase,
                "sql": sql,
                "args": parameters,
            }
        )

    def before(
        self, conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
    ) -> None:
        role = ROLE.get()
        if role is not None:
            # A common DeviceRow-first fix can block the other request during
            # authentication's UPDATE, before any explicit service row lock.
            self.pids[role] = conn.connection.driver_connection.get_server_pid()
        self.record("requested", statement, parameters)

    def after(
        self, conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
    ) -> None:
        self.record("completed", statement, parameters)

    def error(self, context: Any) -> None:
        error = context.original_exception
        self.errors.append(
            {
                "role": ROLE.get(),
                "sqlstate": getattr(error, "sqlstate", getattr(error, "pgcode", None)),
                "error": str(error),
            }
        )

    async def run(self, first: Request, second: Request) -> dict[str, httpx.Response]:
        # No prescribed second lock or inverted order: a corrected request may
        # block on the first common lock, or finish without any lock conflict.
        async with asyncio.timeout(12), asyncio.TaskGroup() as workers:
            first_task = workers.create_task(first.send(), name=f"control-lock-{first.role}")
            await self.held.wait()
            second_task = workers.create_task(second.send(), name=f"control-lock-{second.role}")
            try:
                async with first.api.app.state.database.engine.connect() as observer:
                    while not second_task.done():
                        pid = self.pids.get(second.role)
                        # pg_stat_activity otherwise retains this transaction's
                        # earlier query text while pg_blocking_pids stays fresh.
                        await observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                        rows = (
                            await observer.execute(
                                text(
                                    "SELECT pid, pg_blocking_pids(pid) AS blockers, "
                                    "wait_event_type, wait_event, query FROM pg_stat_activity "
                                    "WHERE datname = current_database() AND pid = :pid"
                                ),
                                {"pid": pid or 0},
                            )
                        ).mappings()
                        row = rows.first()
                        if row is not None and self.pids[first.role] in row["blockers"]:
                            self.wait_edge = dict(row)
                            self.locks_before_release = [
                                dict(lock)
                                for lock in (
                                    await observer.execute(
                                        text(
                                            "SELECT pid, locktype, relation::regclass::text "
                                            "AS relation, transactionid, mode, granted "
                                            "FROM pg_locks WHERE pid IN (:first, :second) "
                                            "ORDER BY pid, locktype, relation, mode"
                                        ),
                                        {"first": self.pids[first.role], "second": pid},
                                    )
                                ).mappings()
                            ]
                            break
            finally:
                self.trace.append({"phase": "barrier_released"})
                self.release.set()
        return {first.role: first_task.result(), second.role: second_task.result()}


async def exercise(
    apis: tuple[Api, Api], monkeypatch: pytest.MonkeyPatch, scenario: str
) -> dict[str, Any]:
    first_api, second_api = apis
    device, auth = await provision(first_api)
    live: dict[str, Any] | None = None
    live_before: dict[str, Any] | None = None
    previous: str | None = None
    if scenario == "queued_cancel":
        previous = await create_read_task(first_api, device)
        claimed = await post(first_api, "/companion/v2/tasks/claim", auth, {"leaseSeconds": 60})
        assert claimed["id"] == previous
        await post(
            first_api,
            f"/companion/v2/tasks/{previous}/complete",
            auth,
            {"leaseId": claimed["leaseId"], "result": {"observed": True}},
        )
    else:
        assert scenario == "live_take_control"
        live = await post(
            second_api,
            f"/api/v1/live/devices/{device}/sessions",
            operator_headers(),
            {"tier": "INTERACTIVE_REMOTE"},
            201,
        )
        assert live["state"] == "VIEWING" and live["capabilities"]["allowsInput"]
        acknowledged = await post(
            second_api,
            f"/companion/v2/fleet-live/{live['sessionId']}/ack",
            auth,
            {"granted": True},
        )
        assert acknowledged["authorization"]["userConfirmedAt"] is not None
    task_id = await create_read_task(first_api, device)
    if scenario == "queued_cancel":
        first = Request(
            first_api,
            "cancel",
            f"/api/v1/platform-tasks/{task_id}:cancel",
            operator_headers(),
            {"reason": "control-lock reproduction"},
        )
        second = Request(
            second_api, "claim", "/companion/v2/tasks/claim", auth, {"leaseSeconds": 60}
        )
    else:
        assert live is not None
        claimed = await post(first_api, "/companion/v2/tasks/claim", auth, {"leaseSeconds": 60})
        assert claimed["id"] == task_id
        heartbeat_path = f"/companion/v2/tasks/{task_id}/heartbeat"
        heartbeat_body = {"leaseId": claimed["leaseId"], "leaseSeconds": 60, "currentStep": 0}
        running = await post(first_api, heartbeat_path, auth, heartbeat_body)
        assert running["status"] == running["businessState"] == "RUNNING"
        status = await second_api.client.get(
            f"/api/v1/live/sessions/{live['sessionId']}",
            headers={**operator_headers(), "X-Live-Session-Token": live["sessionToken"]},
        )
        assert status.status_code == 200, status.text
        live_before = status.json()
        assert live_before is not None
        assert live_before["state"] == "VIEWING" and live_before["capabilities"]["allowsInput"]
        assert live_before["authorization"]["userConfirmedAt"] is not None
        assert datetime.fromisoformat(live_before["expiresAt"]) > datetime.now(UTC)
        first = Request(first_api, "heartbeat", heartbeat_path, auth, heartbeat_body)
        second = Request(
            second_api,
            "take_control",
            f"/api/v1/live/sessions/{live['sessionId']}:take-control",
            {**operator_headers(), "X-Live-Session-Token": live["sessionToken"]},
            None,
        )
    before = await durable(first_api, device)
    if scenario == "queued_cancel":
        assert [row["status"] for row in before["tasks"]] == ["SUCCEEDED", "QUEUED"]
        assert before["lease"]["canceledAt"] is not None
        assert before["lease"]["workflow"] == f"auto/{previous}"
    else:
        assert before["tasks"][0]["status"] == before["tasks"][0]["businessState"] == "RUNNING"
        assert before["lease"]["owner"] == "AUTO" and before["lease"]["canceledAt"] is None
        assert before["lease"]["expiresAt"] > datetime.now(UTC)
        assert before["lease"]["id"] == before["tasks"][0]["leaseId"]
        assert before["tasks"][0]["leaseExpiresAt"] > datetime.now(UTC)

    schedule = LockSchedule(first.role)
    with monkeypatch.context() as scoped:
        schedule.install(scoped, apis)
        try:
            responses = await schedule.run(first, second)
        finally:
            schedule.uninstall(apis)
    after = await durable(first_api, device)
    async with first_api.app.state.database.engine.connect() as observer:
        version = await observer.scalar(text("SHOW server_version"))
        deadlock_timeout = await observer.scalar(text("SHOW deadlock_timeout"))
        lock_timeout = await observer.scalar(text("SHOW lock_timeout"))
        pending = list(
            (
                await observer.execute(
                    text(
                        "SELECT pid, state FROM pg_stat_activity "
                        "WHERE datname = current_database() AND pid != pg_backend_pid() "
                        "AND state != 'idle'"
                    )
                )
            ).mappings()
        )
    assert not pending, pending
    assert not any(
        task.get_name().startswith("control-lock-") and not task.done()
        for task in asyncio.all_tasks()
    )
    assert all(api.app.state.database.engine.pool.checkedout() == 0 for api in apis)
    report = {
        "scenario": scenario,
        "postgres": version,
        "driver": first_api.app.state.database.engine.dialect.driver,
        "pool": type(first_api.app.state.database.engine.pool).__name__,
        "deadlock_timeout": deadlock_timeout,
        "lock_timeout": lock_timeout,
        "pids": schedule.pids,
        "wait_edge": schedule.wait_edge,
        "locksBeforeRelease": schedule.locks_before_release,
        "trace": schedule.trace,
        "errors": schedule.errors,
        "http": {
            role: {"status": response.status_code, "body": response.text}
            for role, response in responses.items()
        },
        "before": before,
        "after": after,
        "liveBefore": live_before,
        "liveState": None
        if live is None
        else second_api.app.state.fleet_live_service.sessions[live["sessionId"]].state,
        "pendingTransactions": pending,
        "checkedOutConnections": 0,
        "remainingWorkers": 0,
    }
    print("CONTROL_LOCK_EVIDENCE " + json.dumps(report, default=str, sort_keys=True))
    return report


@pytest.mark.parametrize("scenario", SCENARIOS)
async def test_control_requests_finish_without_deadlock(
    control_apis: tuple[Api, Api], monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    report = await exercise(control_apis, monkeypatch, scenario)
    assert not report["errors"], (
        "Desired regression: concurrent control requests must not deadlock",
        report["errors"],
        report["http"],
    )
    if scenario == "queued_cancel":
        assert report["http"]["cancel"]["status"] == 200
        assert report["http"]["claim"]["status"] in {200, 204}
        assert report["after"]["tasks"][0] == report["before"]["tasks"][0]
        assert report["after"]["tasks"][1]["businessState"] == "CANCELLED"
        assert report["after"]["lease"]["canceledAt"] is not None
    else:
        assert all(result["status"] == 200 for result in report["http"].values())
        assert report["after"]["tasks"][0]["businessState"] == "PAUSED_WAITING_USER"
        assert report["after"]["lease"]["owner"] == "REMOTE"
        assert report["liveState"] == "REMOTE"
