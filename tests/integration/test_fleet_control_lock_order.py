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
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api import fleet_live as fleet_live_module
from cloudctl_api.db import (
    AccountDeviceBindingRow,
    AuditEventRow,
    DeviceLeaseRow,
    DeviceRow,
    MobileTaskRow,
)
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


async def viewing_session(api: Api, device: str, auth: dict[str, str]) -> dict[str, Any]:
    live = await post(
        api,
        f"/api/v1/live/devices/{device}/sessions",
        operator_headers(),
        {"tier": "INTERACTIVE_REMOTE"},
        201,
    )
    assert live["state"] == "VIEWING" and live["capabilities"]["allowsInput"]
    acknowledged = await post(
        api,
        f"/companion/v2/fleet-live/{live['sessionId']}/ack",
        auth,
        {"granted": True},
    )
    assert acknowledged["authorization"]["userConfirmedAt"] is not None
    return live


def live_headers(live: dict[str, Any]) -> dict[str, str]:
    return {**operator_headers(), "X-Live-Session-Token": live["sessionToken"]}


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
        device_row = await session.get(DeviceRow, device)
        assert device_row is not None
        return {
            "fencingCounter": device_row.fencing_counter,
            "controlEpoch": device_row.control_epoch,
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
                "fencingToken": lease.fencing_token,
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
    apis: tuple[Api, Api],
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    *,
    initial_phase: str = "RUNNING",
    stale_remote: bool = False,
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
        live = await viewing_session(second_api, device, auth)
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
        if initial_phase != "PREFLIGHT":
            running = await post(first_api, heartbeat_path, auth, heartbeat_body)
            assert running["status"] == running["businessState"] == "RUNNING"
        if initial_phase == "RESUME_CHECK":
            await post(
                first_api,
                f"/companion/v2/tasks/{task_id}/events",
                auth,
                {
                    "leaseId": claimed["leaseId"],
                    "sequence": 1,
                    "eventType": "RESUME_CHECK",
                    "stepIndex": 0,
                    "payload": {},
                },
                201,
            )
        if stale_remote:
            await post(
                second_api,
                f"/api/v1/live/sessions/{live['sessionId']}:take-control",
                live_headers(live),
                None,
            )
        status = await second_api.client.get(
            f"/api/v1/live/sessions/{live['sessionId']}",
            headers={**operator_headers(), "X-Live-Session-Token": live["sessionToken"]},
        )
        assert status.status_code == 200, status.text
        live_before = status.json()
        assert live_before is not None
        assert live_before["state"] == ("REMOTE" if stale_remote else "VIEWING")
        assert live_before["capabilities"]["allowsInput"]
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
        expected_runner = "CLAIMED" if initial_phase == "PREFLIGHT" else "RUNNING"
        assert before["tasks"][0]["status"] == expected_runner
        assert before["tasks"][0]["businessState"] == (
            "PAUSED_WAITING_USER" if stale_remote else initial_phase
        )
        assert before["lease"]["owner"] == ("REMOTE" if stale_remote else "AUTO")
        assert before["lease"]["canceledAt"] is None
        assert before["lease"]["expiresAt"] > datetime.now(UTC)
        if not stale_remote:
            assert before["lease"]["id"] == before["tasks"][0]["leaseId"]
        assert before["tasks"][0]["leaseExpiresAt"] > datetime.now(UTC)

    schedule = LockSchedule(first.role)
    with monkeypatch.context() as scoped:
        if stale_remote:
            assert live is not None
            session = second_api.app.state.fleet_live_service.sessions[live["sessionId"]]
            stalled_at = (
                session.last_frame_monotonic
                + fleet_live_module.FRAME_STALE_S
                + fleet_live_module.FRAME_GRACE_S / 2
            )
            scoped.setattr(fleet_live_module, "time", SimpleNamespace(monotonic=lambda: stalled_at))
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
        "initialPhase": initial_phase,
        "staleRemote": stale_remote,
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


@pytest.mark.parametrize("initial_phase", ["PREFLIGHT", "RESUME_CHECK"])
async def test_take_control_locks_tasks_that_heartbeat_can_make_running(
    control_apis: tuple[Api, Api], monkeypatch: pytest.MonkeyPatch, initial_phase: str
) -> None:
    report = await exercise(
        control_apis, monkeypatch, "live_take_control", initial_phase=initial_phase
    )
    assert not report["errors"], report["errors"]
    assert all(result["status"] == 200 for result in report["http"].values()), report["http"]
    assert report["after"]["tasks"][0]["status"] == "RUNNING"
    assert report["after"]["tasks"][0]["businessState"] == "PAUSED_WAITING_USER"
    assert report["after"]["lease"]["owner"] == report["liveState"] == "REMOTE"
    assert report["after"]["fencingCounter"] == report["before"]["fencingCounter"] + 1


async def test_stale_remote_sweep_and_heartbeat_finish_without_deadlock(
    control_apis: tuple[Api, Api], monkeypatch: pytest.MonkeyPatch
) -> None:
    report = await exercise(control_apis, monkeypatch, "live_take_control", stale_remote=True)
    assert not report["errors"], report["errors"]
    assert all(result["status"] == 200 for result in report["http"].values()), report["http"]
    assert report["after"]["tasks"][0]["businessState"] == "PAUSED_WAITING_USER"
    assert report["after"]["lease"]["owner"] == report["liveState"] == "REMOTE"
    assert report["after"]["fencingCounter"] == report["before"]["fencingCounter"] + 1


async def task_snapshot(api: Api, task_id: str) -> dict[str, Any] | None:
    async with api.app.state.database.unit_of_work() as session:
        task = await session.get(MobileTaskRow, task_id)
        if task is None:
            return None
        return {
            "tenant": task.tenant_id,
            "device": task.device_id,
            "runner": task.status,
            "business": task.business_state,
            "lease": task.lease_id,
            "expires": task.lease_expires_at,
            "payload": task.command_payload,
            "steps": task.steps,
            "result": task.result,
            "mode": task.control_mode,
            "resumeCount": task.resume_count,
            "account": task.account_id,
            "bindingVersion": task.binding_version,
        }


async def cancel_audits(api: Api, task_id: str) -> list[dict[str, Any]]:
    async with api.app.state.database.unit_of_work() as session:
        return [
            {"action": row.action, "metadata": row.metadata_json}
            for row in await session.scalars(
                select(AuditEventRow)
                .where(
                    AuditEventRow.resource_id == task_id,
                    AuditEventRow.action.in_(
                        ("platform.task.cancelled", "platform.task.cancel_requested")
                    ),
                )
                .order_by(AuditEventRow.occurred_at, AuditEventRow.id)
            )
        ]


@pytest.mark.parametrize(
    "changed", ["running", "succeeded", "commit_intent", "device", "tenant", "deleted"]
)
async def test_cancel_refreshes_state_and_rechecks_identity_under_lock(
    control_apis: tuple[Api, Api], monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    api, other = control_apis
    device, auth = await provision(api)
    task_id = await create_read_task(api, device)
    located, release = asyncio.Event(), asyncio.Event()
    original = AsyncSession.get

    async def get(session: AsyncSession, entity: Any, ident: Any, **kwargs: Any) -> Any:
        row = await original(session, entity, ident, **kwargs)
        if (
            ROLE.get() == "cancel"
            and entity is MobileTaskRow
            and ident == task_id
            and not kwargs.get("with_for_update")
            and not located.is_set()
        ):
            assert row is not None and row.business_state == "QUEUED"
            located.set()
            await release.wait()
        return row

    with monkeypatch.context() as scoped:
        scoped.setattr(AsyncSession, "get", get)
        async with asyncio.timeout(12), asyncio.TaskGroup() as workers:
            cancel = workers.create_task(
                Request(
                    api,
                    "cancel",
                    f"/api/v1/platform-tasks/{task_id}:cancel",
                    operator_headers(),
                    {"reason": "fresh-under-lock"},
                ).send()
            )
            try:
                await located.wait()
                if changed in {"running", "succeeded"}:
                    claimed = await post(
                        other, "/companion/v2/tasks/claim", auth, {"leaseSeconds": 60}
                    )
                    assert claimed["id"] == task_id
                    if changed == "running":
                        await post(
                            other,
                            f"/companion/v2/tasks/{task_id}/heartbeat",
                            auth,
                            {"leaseId": claimed["leaseId"], "leaseSeconds": 60},
                        )
                    else:
                        await post(
                            other,
                            f"/companion/v2/tasks/{task_id}/complete",
                            auth,
                            {"leaseId": claimed["leaseId"], "result": {"observed": True}},
                        )
                else:
                    moved_device = None
                    if changed == "device":
                        moved_device = await post(
                            other,
                            "/api/v1/mobile/devices",
                            operator_headers(),
                            {"logicalName": "moved-task-device", "androidVersion": "14"},
                            201,
                        )
                    # Inject otherwise immutable-identity/legacy-marker faults
                    # only in this owned database while cancel holds no row lock.
                    async with other.app.state.database.unit_of_work() as session:
                        task = await session.get(MobileTaskRow, task_id)
                        assert task is not None
                        if changed == "commit_intent":
                            task.command_payload = {"commitIntent": True}
                        elif changed == "device":
                            assert moved_device is not None
                            task.device_id = moved_device["id"]
                        elif changed == "tenant":
                            task.tenant_id = "00000000-0000-7000-8000-000000000999"
                        else:
                            await session.delete(task)
                before = await task_snapshot(other, task_id)
                before_lease = (await durable(other, device))["lease"]
            finally:
                release.set()
        response = cancel.result()

    after = await task_snapshot(other, task_id)
    audits = await cancel_audits(other, task_id)
    assert (await durable(other, device))["lease"] == before_lease
    if changed == "running":
        assert response.status_code == 200, response.text
        assert response.json()["state"] == "CANCEL_REQUESTED"
        assert before is not None and after is not None
        assert after["runner"] == "RUNNING" and after["business"] == "CANCEL_REQUESTED"
        for field_name in ("lease", "expires", "result", "payload", "mode"):
            assert after[field_name] == before[field_name]
        assert len(audits) == 1 and audits[0]["action"] == "platform.task.cancel_requested"
        assert audits[0]["metadata"]["controlRevision"] == 1
    else:
        expected = 409 if changed in {"succeeded", "commit_intent"} else 404
        assert response.status_code == expected, response.text
        assert after == before
        assert audits == []


async def test_cancel_preserves_permission_tenant_idempotency_and_remote_occupation(
    control_apis: tuple[Api, Api],
) -> None:
    api, _ = control_apis
    device, auth = await provision(api)
    live = await viewing_session(api, device, auth)
    task_id = await create_read_task(api, device)
    await post(
        api, f"/api/v1/live/sessions/{live['sessionId']}:take-control", live_headers(live), None
    )
    before = await durable(api, device)
    assert before["lease"]["owner"] == "REMOTE"
    path = f"/api/v1/platform-tasks/{task_id}:cancel"
    for headers, expected in (
        ({**operator_headers(), "X-Roles": "content_viewer"}, 403),
        (
            {**operator_headers(), "X-Tenant-Id": "00000000-0000-7000-8000-000000000999"},
            404,
        ),
    ):
        denied = await api.client.post(path, headers=headers, json={})
        assert denied.status_code == expected, denied.text
        assert await durable(api, device) == before
        assert await cancel_audits(api, task_id) == []
    cancelled = await post(api, path, operator_headers(), {"reason": "operator canceled"})
    replay = await post(api, path, operator_headers(), {"reason": "duplicate request"})
    assert replay == cancelled
    assert cancelled["state"] == "CANCELLED" and cancelled["controlRevision"] == 1
    after = await durable(api, device)
    assert after["lease"] == before["lease"]
    assert after["fencingCounter"] == before["fencingCounter"]
    audits = await cancel_audits(api, task_id)
    assert len(audits) == 1 and audits[0]["action"] == "platform.task.cancelled"
    assert audits[0]["metadata"]["occupationReleased"] is False


async def test_take_control_prelocks_without_pausing_preflight_or_queued(
    control_apis: tuple[Api, Api],
) -> None:
    api, _ = control_apis
    device, auth = await provision(api)
    live = await viewing_session(api, device, auth)
    first = await create_read_task(api, device)
    await create_read_task(api, device)
    claimed = await post(api, "/companion/v2/tasks/claim", auth, {"leaseSeconds": 60})
    assert claimed["id"] == first
    before = await durable(api, device)
    assert [task["businessState"] for task in before["tasks"]] == ["PREFLIGHT", "QUEUED"]
    controlled = await post(
        api, f"/api/v1/live/sessions/{live['sessionId']}:take-control", live_headers(live), None
    )
    after = await durable(api, device)
    assert after["tasks"] == before["tasks"]
    assert controlled["state"] == after["lease"]["owner"] == "REMOTE"
    assert after["fencingCounter"] == before["fencingCounter"] + 1
    assert after["lease"]["fencingToken"] == controlled["lease"]["epoch"]


async def test_take_control_conflicting_remote_owner_rejects_before_mutation(
    control_apis: tuple[Api, Api],
) -> None:
    api, other = control_apis
    device, auth = await provision(api)
    older = await viewing_session(api, device, auth)
    task_id = await create_read_task(api, device)
    claimed = await post(api, "/companion/v2/tasks/claim", auth, {"leaseSeconds": 60})
    assert claimed["id"] == task_id
    await post(
        api,
        f"/companion/v2/tasks/{task_id}/heartbeat",
        auth,
        {"leaseId": claimed["leaseId"], "leaseSeconds": 60},
    )
    newer = await viewing_session(other, device, auth)
    control_path = f"/api/v1/live/sessions/{newer['sessionId']}:take-control"
    controlled = await post(other, control_path, live_headers(newer), None)
    before = await durable(api, device)
    rejected = await api.client.post(
        f"/api/v1/live/sessions/{older['sessionId']}:take-control", headers=live_headers(older)
    )
    assert rejected.status_code == 409 and "LIVE_REMOTE_HELD" in rejected.text
    assert await durable(api, device) == before
    assert api.app.state.fleet_live_service.sessions[older["sessionId"]].state == "VIEWING"
    replay = await post(other, control_path, live_headers(newer), None)
    assert replay == controlled
    assert await durable(api, device) == before
    assert before["lease"]["workflow"] == f"live/{newer['sessionId']}"


@pytest.mark.parametrize("control", ["cancel", "take_control"])
async def test_paused_resume_and_control_finish_without_lock_inversion(
    control_apis: tuple[Api, Api], monkeypatch: pytest.MonkeyPatch, control: str
) -> None:
    api, other = control_apis
    device, auth = await provision(api)
    live = await viewing_session(other, device, auth) if control == "take_control" else None
    task_id = await create_read_task(api, device)
    claimed = await post(api, "/companion/v2/tasks/claim", auth, {"leaseSeconds": 60})
    assert claimed["id"] == task_id
    await post(
        api,
        f"/companion/v2/tasks/{task_id}/heartbeat",
        auth,
        {"leaseId": claimed["leaseId"], "leaseSeconds": 60},
    )
    paused = await post(
        api,
        f"/api/v1/platform-tasks/{task_id}:pause",
        operator_headers(),
        {"reason": "operator pause before verified resume"},
    )
    assert paused["state"] == "PAUSE_REQUESTED"
    acknowledged = await post(
        api, f"/api/v1/platform-tasks/{task_id}:ack-paused", operator_headers(), {}
    )
    assert acknowledged["state"] == "PAUSED_WAITING_USER"
    before = await durable(api, device)
    task_before = await task_snapshot(api, task_id)
    assert task_before is not None
    assert task_before["runner"] == "RUNNING"
    assert task_before["business"] == "PAUSED_WAITING_USER"
    assert not task_before["payload"].get("commitIntent")
    first = Request(
        api,
        "resume",
        f"/api/v1/platform-tasks/{task_id}:resume",
        operator_headers(),
        {"reason": "operator verified current page", "pageVerified": True},
    )
    if control == "cancel":
        second = Request(
            other,
            control,
            f"/api/v1/platform-tasks/{task_id}:cancel",
            operator_headers(),
            {"reason": "concurrent operator cancellation"},
        )
    else:
        assert live is not None
        second = Request(
            other,
            control,
            f"/api/v1/live/sessions/{live['sessionId']}:take-control",
            live_headers(live),
            None,
        )
    schedule = LockSchedule(first.role)
    with monkeypatch.context() as scoped:
        schedule.install(scoped, control_apis)
        try:
            responses = await schedule.run(first, second)
        finally:
            schedule.uninstall(control_apis)
    after = await durable(api, device)
    assert all(app.app.state.database.engine.pool.checkedout() == 0 for app in control_apis)
    assert not any(
        task.get_name().startswith("control-lock-") and not task.done()
        for task in asyncio.all_tasks()
    )
    report = {
        "scenario": f"paused_resume_vs_{control}",
        "before": before,
        "after": after,
        "taskBefore": task_before,
        "taskAfter": await task_snapshot(api, task_id),
        "trace": schedule.trace,
        "pids": schedule.pids,
        "wait_edge": schedule.wait_edge,
        "locksBeforeRelease": schedule.locks_before_release,
        "errors": schedule.errors,
        "http": {
            role: {"status": response.status_code, "body": response.text}
            for role, response in responses.items()
        },
        "liveState": None
        if live is None
        else other.app.state.fleet_live_service.sessions[live["sessionId"]].state,
        "remainingWorkers": 0,
        "checkedOutConnections": 0,
    }
    print("CONTROL_LOCK_RESUME_EVIDENCE " + json.dumps(report, default=str, sort_keys=True))
    assert not report["errors"], report
    assert responses[control].status_code == 200, report
    assert responses["resume"].status_code == 200, report
    assert len(after["tasks"]) == 1 and after["tasks"][0]["id"] == task_id
    resumed = responses["resume"].json()
    assert resumed["state"] == "RESUME_CHECK" and resumed["resumeCount"] == 1
    assert resumed["controlEpoch"] == before["fencingCounter"] + 1
    assert after["controlEpoch"] == before["controlEpoch"] + 1
    task_after = report["taskAfter"]
    assert task_after is not None
    for key in ("tenant", "device", "payload", "result", "account", "bindingVersion"):
        assert task_after[key] == task_before[key]
    assert task_after["resumeCount"] == task_before["resumeCount"] + 1
    assert task_after["lease"] != task_before["lease"]
    if control == "cancel":
        assert after["tasks"][0]["businessState"] == "CANCEL_REQUESTED"
        assert after["lease"]["owner"] == "AUTO"
        assert after["lease"]["id"] == after["tasks"][0]["leaseId"]
        assert after["fencingCounter"] == before["fencingCounter"] + 1
    else:
        assert after["tasks"][0]["businessState"] == "RESUME_CHECK"
        assert after["tasks"][0]["status"] == "RUNNING"
        assert report["liveState"] == "REMOTE"
        assert live is not None
        assert after["lease"]["owner"] == "REMOTE"
        assert after["lease"]["workflow"] == f"live/{live['sessionId']}"
        assert after["fencingCounter"] == before["fencingCounter"] + 2


async def paused_task(api: Api, device: str, auth: dict[str, str]) -> str:
    task_id = await create_read_task(api, device)
    claimed = await post(api, "/companion/v2/tasks/claim", auth, {"leaseSeconds": 60})
    assert claimed["id"] == task_id
    await post(
        api,
        f"/companion/v2/tasks/{task_id}/heartbeat",
        auth,
        {"leaseId": claimed["leaseId"], "leaseSeconds": 60},
    )
    await post(
        api,
        f"/api/v1/platform-tasks/{task_id}:pause",
        operator_headers(),
        {"reason": "prepare verified resume"},
    )
    paused = await post(api, f"/api/v1/platform-tasks/{task_id}:ack-paused", operator_headers(), {})
    assert paused["state"] == "PAUSED_WAITING_USER"
    return task_id


async def audit_snapshot(api: Api) -> list[dict[str, Any]]:
    async with api.app.state.database.unit_of_work() as session:
        return [
            {"id": row.id, "action": row.action, "metadata": row.metadata_json}
            for row in await session.scalars(
                select(AuditEventRow).order_by(AuditEventRow.occurred_at, AuditEventRow.id)
            )
        ]


@pytest.mark.parametrize(
    "changed",
    [
        "cancel",
        "resume",
        "commit_intent",
        "device",
        "tenant",
        "deleted",
        "binding_version",
        "binding_missing",
    ],
)
async def test_resume_refreshes_state_and_identity_before_mutation(
    control_apis: tuple[Api, Api], monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    api, other = control_apis
    device, auth = await provision(api)
    task_id = await paused_task(api, device, auth)
    account_id = None
    if changed.startswith("binding"):
        account = await post(
            api,
            "/api/v1/accounts",
            operator_headers(),
            {
                "platform": "xianyu",
                "externalSubjectRef": "resume-lock-test",
                "displayLabel": "resume-lock-test",
                "secretRef": "vault://cloudctl/accounts/resume-lock-test",
                "authorizationBasis": "Owned software test fixture.",
            },
            201,
        )
        account_id = account["id"]
        bound = await post(
            api,
            f"/api/v1/accounts/{account_id}/bindings",
            operator_headers(),
            {"deviceId": device, "confirmationNote": "Owned software test fixture."},
            201,
        )
        # Attach account metadata to the read-only task in the owned database;
        # no platform publication or external account operation is performed.
        async with api.app.state.database.unit_of_work() as session:
            task = await session.get(MobileTaskRow, task_id)
            assert task is not None
            task.account_id = account_id
            task.binding_version = bound["bindingVersion"]

    located, release = asyncio.Event(), asyncio.Event()
    original = AsyncSession.get

    async def get(session: AsyncSession, entity: Any, ident: Any, **kwargs: Any) -> Any:
        row = await original(session, entity, ident, **kwargs)
        if (
            ROLE.get() == "resume-fresh"
            and entity is MobileTaskRow
            and ident == task_id
            and not kwargs.get("with_for_update")
            and not located.is_set()
        ):
            assert row is not None and row.business_state == "PAUSED_WAITING_USER"
            located.set()
            await release.wait()
        return row

    errors: list[str] = []

    def sql_error(context: Any) -> None:
        errors.append(str(context.original_exception))

    engine = api.app.state.database.engine.sync_engine
    event.listen(engine, "handle_error", sql_error)
    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(AsyncSession, "get", get)
            async with asyncio.timeout(12), asyncio.TaskGroup() as workers:
                request = workers.create_task(
                    Request(
                        api,
                        "resume-fresh",
                        f"/api/v1/platform-tasks/{task_id}:resume",
                        operator_headers(),
                        {"reason": "verified", "pageVerified": True},
                    ).send()
                )
                try:
                    await located.wait()
                    if changed in {"cancel", "resume"}:
                        result = await post(
                            other,
                            f"/api/v1/platform-tasks/{task_id}:{changed}",
                            operator_headers(),
                            {"reason": "concurrent control", "pageVerified": True},
                        )
                        assert result["state"] == (
                            "CANCELLED" if changed == "cancel" else "RESUME_CHECK"
                        )
                    else:
                        moved = None
                        if changed == "device":
                            moved = await post(
                                other,
                                "/api/v1/mobile/devices",
                                operator_headers(),
                                {"logicalName": "resume-moved", "androidVersion": "14"},
                                201,
                            )
                        async with other.app.state.database.unit_of_work() as session:
                            task = await session.get(MobileTaskRow, task_id)
                            assert task is not None
                            if changed == "commit_intent":
                                task.command_payload = {"commitIntent": True}
                            elif changed == "device":
                                assert moved is not None
                                task.device_id = moved["id"]
                            elif changed == "tenant":
                                task.tenant_id = "00000000-0000-7000-8000-000000000999"
                            elif changed == "deleted":
                                await session.delete(task)
                            else:
                                binding = await session.scalar(
                                    select(AccountDeviceBindingRow).where(
                                        AccountDeviceBindingRow.account_id == account_id,
                                        AccountDeviceBindingRow.device_id == device,
                                    )
                                )
                                assert binding is not None
                                if changed == "binding_missing":
                                    await session.delete(binding)
                                else:
                                    binding.binding_version += 1
                    before = await task_snapshot(other, task_id)
                    durable_before = await durable(other, device)
                    audits_before = await audit_snapshot(other)
                finally:
                    release.set()
            response = request.result()
    finally:
        event.remove(engine, "handle_error", sql_error)
    expected = 404 if changed in {"device", "tenant", "deleted"} else 409
    assert response.status_code == expected, response.text
    assert not errors, errors
    assert await task_snapshot(other, task_id) == before
    assert await durable(other, device) == durable_before
    assert await audit_snapshot(other) == audits_before
    assert all(item.app.state.database.engine.pool.checkedout() == 0 for item in control_apis)


@pytest.mark.parametrize("guard", ["permission", "tenant", "page_verified", "commit_intent"])
async def test_resume_rejection_preserves_task_lease_counters_and_audit(
    control_apis: tuple[Api, Api], guard: str
) -> None:
    api, _ = control_apis
    device, auth = await provision(api)
    task_id = await paused_task(api, device, auth)
    headers = operator_headers()
    if guard == "permission":
        headers["X-Roles"] = "content_viewer"
    elif guard == "tenant":
        headers["X-Tenant-Id"] = "00000000-0000-7000-8000-000000000999"
    elif guard == "commit_intent":
        async with api.app.state.database.unit_of_work() as session:
            task = await session.get(MobileTaskRow, task_id)
            assert task is not None
            task.command_payload = {"commitIntent": True}
    before = await durable(api, device)
    task_before = await task_snapshot(api, task_id)
    audits_before = await audit_snapshot(api)
    response = await api.client.post(
        f"/api/v1/platform-tasks/{task_id}:resume",
        headers=headers,
        json={"reason": "guard probe", "pageVerified": guard != "page_verified"},
    )
    expected = {"permission": 403, "tenant": 404, "page_verified": 422, "commit_intent": 409}
    assert response.status_code == expected[guard], response.text
    assert await durable(api, device) == before
    assert await task_snapshot(api, task_id) == task_before
    assert await audit_snapshot(api) == audits_before


@pytest.mark.parametrize("guard", ["tier", "consent", "sweep_close"])
async def test_take_control_preserves_rejection_and_sweep_commit_semantics(
    control_apis: tuple[Api, Api], monkeypatch: pytest.MonkeyPatch, guard: str
) -> None:
    api, _ = control_apis
    device, auth = await provision(api)
    live = await post(
        api,
        f"/api/v1/live/devices/{device}/sessions",
        operator_headers(),
        {"tier": "JPEG_PREVIEW" if guard == "tier" else "INTERACTIVE_REMOTE"},
        201,
    )
    task_id = await create_read_task(api, device)
    claimed = await post(api, "/companion/v2/tasks/claim", auth, {"leaseSeconds": 60})
    assert claimed["id"] == task_id
    await post(
        api,
        f"/companion/v2/tasks/{task_id}/heartbeat",
        auth,
        {"leaseId": claimed["leaseId"], "leaseSeconds": 60},
    )
    if guard == "sweep_close":
        await post(
            api, f"/companion/v2/fleet-live/{live['sessionId']}/ack", auth, {"granted": True}
        )
        await post(
            api,
            f"/api/v1/live/sessions/{live['sessionId']}:take-control",
            live_headers(live),
            None,
        )
    before = await durable(api, device)
    assert before["tasks"][0]["businessState"] == (
        "PAUSED_WAITING_USER" if guard == "sweep_close" else "RUNNING"
    )
    audits_before = await audit_snapshot(api)
    session = api.app.state.fleet_live_service.sessions[live["sessionId"]]
    with monkeypatch.context() as scoped:
        if guard == "sweep_close":
            expired = session.established_monotonic + fleet_live_module.SESSION_HARD_LIMIT_S + 1
            scoped.setattr(fleet_live_module, "time", SimpleNamespace(monotonic=lambda: expired))
        response = await api.client.post(
            f"/api/v1/live/sessions/{live['sessionId']}:take-control",
            headers=live_headers(live),
        )
    expected = {
        "tier": (403, "LIVE_INPUT_FORBIDDEN"),
        "consent": (428, "LIVE_AUTH_REQUIRED"),
        "sweep_close": (410, "LIVE_SESSION_TERMINAL"),
    }
    status, code = expected[guard]
    assert response.status_code == status, response.text
    assert response.json()["code"] == code
    after = await durable(api, device)
    audits_after = await audit_snapshot(api)
    if guard == "sweep_close":
        assert session.closed and session.closed_cause == "TIMEOUT_30M"
        assert after["lease"]["canceledAt"] is not None
        assert before["lease"]["canceledAt"] is None
        assert after["lease"]["id"] == before["lease"]["id"]
        assert after["fencingCounter"] == before["fencingCounter"]
        assert after["tasks"] == before["tasks"]
        assert len(audits_after) == len(audits_before) + 1
        assert audits_after[-1]["action"] == "live.session.closed"
    else:
        assert after == before
        assert audits_after == audits_before
        assert session.state == "VIEWING"
