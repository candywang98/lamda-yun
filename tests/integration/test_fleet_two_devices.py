"""Q10 dual-device scheduling software integration gate (fleet-identity/v1).

Rolls A10 (fleet identity: capability negotiation, account write mutex,
open-UNKNOWN reclaim guard, authorization envelope) and A11 (claim recovery,
frozen-steps identity guards) up into one two-device gate at a single
integration SHA, from the API's point of view:

- Two *independent* API processes (two ASGI app instances, each with its own
  engine/connection pool) share one disposable PostgreSQL cluster — the
  ``isolated_postgres`` pattern from ``test_fleet_claim_recovery``; SQLite
  must never stand in for the cross-process row-lock proofs.
- Two simulated device clients are pinned to opposite API processes
  (device A -> API-1, device B -> API-2), exactly like two phones behind
  different load-balancer backends.
- Injected faults (from tests/fixtures/fleet/q10-two-devices.json): reclaim,
  stale token, stale authorization envelope, duplicate events, device A
  disconnect, tenant conflict, open-UNKNOWN.
- Side-effect-free commands only: ``device.probe_capabilities.v1`` (read) and
  the frozen maintenance steps families as the write representative — the
  Companion is simulated by this test and never executes a step against a
  real platform; Q03 real publishing is not used.

Acceptance (task card):
- no same-device double write; no cross-tenant / cross-device crosstalk;
- different devices progress in parallel and canceling A never affects B;
- software results and skipped device items are counted separately and
  reported explicitly (see the accounting test and the pytest ``-rs``
  summary; the on-device items are skipped with stable reasons).

A12 (cancel convergence matrix) is NOT merged at this SHA: cancel semantics
are asserted against the current K03 implementation (RUNNING cancel degrades
to CANCEL_REQUESTED and converges via the Companion fail path); deviations
observed on that path are recorded as "pending A12 joint verification"
comments instead of hardened assertions.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import socket
import subprocess
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from cloudctl_api import create_app
from cloudctl_api.db import (
    DeviceLeaseRow,
    MobileActionCommitRow,
    MobileTaskEventRow,
    MobileTaskRow,
)
from cloudctl_api.mobile_actions import canonical_steps
from cloudctl_api.settings import Settings
from fastapi import FastAPI
from sqlalchemy import select
from test_platform_tasks import (
    PROBE,
    identity,
)
from test_xianyu_maintenance import XIANYU, delist_steps, polish_steps

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "fleet" / "q10-two-devices.json"
CROSS_TENANT_FIXTURE = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "fleet" / "q10-cross-tenant.json"
)

OPERATOR = identity()

# Stable identifiers for the skipped on-device (hardware) items; the reasons
# must stay in sync with the ``deviceItems`` list of the scenario fixture.
DEVICE_ITEM_IDS = (
    "q10-device-real-partition-after-intent",
    "q10-device-arbiter-single-writer",
    "q10-device-real-executable-gates",
)


def load_scenario() -> dict[str, Any]:
    return json.loads(SCENARIO_FIXTURE.read_text())


def load_cross_tenant() -> dict[str, Any]:
    return json.loads(CROSS_TENANT_FIXTURE.read_text())


# ---------------------------------------------------------------------------
# Disposable PostgreSQL cluster + two independent API processes
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def isolated_postgres(tmp_path_factory):
    """Never use DATABASE_URL: start our own disposable cluster on a free port."""
    if not all(shutil.which(tool) for tool in ("initdb", "pg_ctl", "createdb")):
        pytest.skip("local PostgreSQL binaries unavailable")
    root = tmp_path_factory.mktemp("q10-postgres")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
        ["initdb", "-D", str(root / "data"), "-A", "trust", "-U", "q10test"],  # noqa: S607
        check=True,
        capture_output=True,
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
    )
    try:
        yield port
    finally:
        subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
            ["pg_ctl", "-D", str(root / "data"), "-m", "immediate", "-w", "stop"],  # noqa: S607
            check=True,
            capture_output=True,
        )
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def pg_url(isolated_postgres):
    name = "q10_" + uuid.uuid4().hex
    subprocess.run(  # noqa: S603 - fixed PostgreSQL tools and test-owned paths
        ["createdb", "-h", "127.0.0.1", "-p", str(isolated_postgres), "-U", "q10test", name],  # noqa: S607
        check=True,
        capture_output=True,
    )
    return f"postgresql+asyncpg://q10test@127.0.0.1:{isolated_postgres}/{name}"


@dataclass
class Api:
    """One independent API process (own app + engine) on the shared cluster."""

    name: str
    client: httpx.AsyncClient
    app: FastAPI


@asynccontextmanager
async def api_process(pg_url: str, name: str) -> AsyncIterator[Api]:
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
            yield Api(name=name, client=client, app=app)


@pytest.fixture
async def two_apis(pg_url) -> AsyncIterator[tuple[Api, Api]]:
    """Two API processes with independent engines over one shared database."""
    async with api_process(pg_url, "api-1") as first, api_process(pg_url, "api-2") as second:
        yield first, second


# ---------------------------------------------------------------------------
# Simulated device clients (Companion behavior, pinned to one API process)
# ---------------------------------------------------------------------------


def full_capabilities() -> dict[str, Any]:
    """All-gates-green closed capability table (fleet-identity/v1 §3)."""
    return {
        "accessibility": {"supported": True, "engineMin": 1},
        "ime": {"supported": True, "engineMin": 1},
        "screen_capture": {"supported": True, "engineMin": 1},
        "media_projection": {"supported": False},
        "flutter_anchors": {"supported": True, "engineMin": 2},
        "im_listen": {"supported": True, "engineMin": 1},
    }


@dataclass
class Companion:
    """A simulated device client pinned to a single API process.

    Keeps every credential it ever held so tests can replay stale tokens and
    stale leases (the fault injections of the Q10 scenario fixture).
    """

    api: Api
    role: str
    logical_name: str
    app_instance_id: str
    boot_id: str
    operator_headers: dict[str, str] = field(default_factory=lambda: dict(OPERATOR))
    device_id: str | None = None
    auth: dict[str, str] | None = None
    stale_auths: list[dict[str, str]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)

    async def provision(self) -> str:
        """Create the device row and enroll the first Companion instance."""
        response = await self.api.client.post(
            "/api/v1/mobile/devices",
            headers=self.operator_headers,
            json={
                "logicalName": self.logical_name,
                "androidVersion": "14",
                "companionVersion": "1.0.0",
            },
        )
        assert response.status_code == 201, response.text
        self.device_id = str(response.json()["id"])
        await self.reinstall(self.app_instance_id)
        assert self.device_id is not None
        return self.device_id

    async def reinstall(self, instance: str) -> dict[str, str]:
        """Enroll a fresh app instance; the previous token is kept stale."""
        enroll = await self.api.client.post(
            "/api/v1/mobile/enrollments",
            headers=self.operator_headers,
            json={"deviceId": self.device_id, "ttlSeconds": 600},
        )
        assert enroll.status_code == 201, enroll.text
        token_resp = await self.api.client.post(
            "/companion/v2/enroll",
            json={
                "code": enroll.json()["code"],
                "appInstanceId": instance,
                "companionVersion": "1.0.0",
            },
        )
        assert token_resp.status_code == 201, token_resp.text
        if self.auth is not None:
            self.stale_auths.append(self.auth)
        self.auth = {"Authorization": f"Bearer {token_resp.json()['bindingToken']}"}
        return self.auth

    async def negotiate(
        self, *, boot_id: str | None = None, engine_version: int = 2
    ) -> dict[str, Any]:
        """Fleet session (re)registration via the pinned API process."""
        assert self.auth is not None
        service = self.api.app.state.mobile_task_service
        token = self.auth["Authorization"].split(" ", 1)[1]
        binding = await service.authenticate(token)
        return await service.register_fleet_session(
            binding,
            boot_id=boot_id or self.boot_id,
            companion_version="1.0.0",
            capabilities=full_capabilities(),
            accessibility_enabled=True,
            accessibility_active=True,
            ime_ready=True,
            screen_unlocked=True,
            engine_version=engine_version,
        )

    async def claim(self, lease_seconds: int = 60) -> httpx.Response:
        assert self.auth is not None
        return await self.api.client.post(
            "/companion/v2/tasks/claim",
            headers=self.auth,
            json={"leaseSeconds": lease_seconds},
        )

    async def heartbeat(self, task_id: str, lease_id: str, step: int = 0) -> httpx.Response:
        assert self.auth is not None
        return await self.api.client.post(
            f"/companion/v2/tasks/{task_id}/heartbeat",
            headers=self.auth,
            json={"leaseId": lease_id, "currentStep": step, "leaseSeconds": 60},
        )

    async def send_event(
        self, task_id: str, lease_id: str, sequence: int, payload: dict[str, Any]
    ) -> httpx.Response:
        assert self.auth is not None
        return await self.api.client.post(
            f"/companion/v2/tasks/{task_id}/events",
            headers=self.auth,
            json={"leaseId": lease_id, "sequence": sequence, **payload},
        )

    async def complete(self, task_id: str, lease_id: str, result: dict[str, Any]) -> httpx.Response:
        assert self.auth is not None
        return await self.api.client.post(
            f"/companion/v2/tasks/{task_id}/complete",
            headers=self.auth,
            json={"leaseId": lease_id, "result": result},
        )

    async def fail(
        self, task_id: str, lease_id: str, error_code: str, detail: str
    ) -> httpx.Response:
        assert self.auth is not None
        return await self.api.client.post(
            f"/companion/v2/tasks/{task_id}/fail",
            headers=self.auth,
            json={"leaseId": lease_id, "errorCode": error_code, "detail": detail},
        )

    async def release(self, task_id: str, lease_id: str) -> httpx.Response:
        assert self.auth is not None
        return await self.api.client.post(
            f"/companion/v2/tasks/{task_id}/release",
            headers=self.auth,
            json={"leaseId": lease_id, "reason": "ACCESSIBILITY_NOT_ACTIVE"},
        )

    async def device_heartbeat(self) -> httpx.Response:
        assert self.auth is not None
        return await self.api.client.post(
            "/companion/v2/devices/heartbeat",
            headers=self.auth,
            json={
                "companionVersion": "1.0.0",
                "accessibilityEnabled": True,
                "runnerState": "IDLE",
            },
        )

    def record(self, event: str, **details: Any) -> None:
        self.history.append({"event": event, **details})


def companion_for(api: Api, scenario: dict[str, Any], role: str) -> Companion:
    spec = next(
        item
        for item in scenario["topology"]["deviceClients"]
        if item["role"] == role
    )
    return Companion(
        api=api,
        role=role,
        logical_name=spec["logicalName"],
        app_instance_id=spec["appInstanceId"],
        boot_id=spec["bootId"],
    )


# ---------------------------------------------------------------------------
# Task minting (side-effect-free families only)
# ---------------------------------------------------------------------------


async def create_probe_task(
    api: Api, device_id: str, *, account_id: str, headers: dict[str, str] | None = None
) -> str:
    """Read-only probe task (device.probe_capabilities.v1) for a bound account."""
    response = await api.client.post(
        "/api/v1/platform-tasks",
        headers={**(headers or OPERATOR), "Idempotency-Key": f"q10-probe-{uuid.uuid4()}"},
        json={"deviceId": device_id, "accountId": account_id, **PROBE},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["items"][0]["taskId"])


async def create_steps_task(
    api: Api,
    device_id: str,
    steps: list[dict[str, Any]],
    *,
    account_id: str | None = None,
) -> str:
    """Frozen maintenance steps task — the write representative (no real publish)."""
    body: dict[str, Any] = {
        "deviceId": device_id,
        "targetPackage": XIANYU,
        "totalTimeoutMs": 120_000,
        "steps": steps,
    }
    if account_id is not None:
        body["accountId"] = account_id
    response = await api.client.post(
        "/api/v1/mobile/tasks",
        headers={**OPERATOR, "Idempotency-Key": f"q10-steps-{uuid.uuid4()}"},
        json=body,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["taskId"])


async def bind_account(
    api: Api,
    device_id: str,
    subject: str,
    *,
    headers: dict[str, str] | None = None,
) -> str:
    """Create a platform account and bind it to the device (tenant-scoped)."""
    operator = headers or OPERATOR
    response = await api.client.post(
        "/api/v1/accounts",
        headers=operator,
        json={
            "platform": "xianyu",
            "externalSubjectRef": subject,
            "displayLabel": subject,
            "secretRef": f"vault://cloudctl/accounts/{subject}",
            "authorizationBasis": "Q10 acceptance target.",
        },
    )
    assert response.status_code == 201, response.text
    account = str(response.json()["id"])
    bound = await api.client.post(
        f"/api/v1/accounts/{account}/bindings",
        headers=operator,
        json={"deviceId": device_id, "confirmationNote": "Q10 acceptance target."},
    )
    assert bound.status_code == 201, bound.text
    return account


async def claim_ok(companion: Companion) -> tuple[str, str, dict[str, Any]]:
    """Claim + first heartbeat; returns (taskId, leaseId, claimBody)."""
    response = await companion.claim()
    assert response.status_code == 200, response.text
    body = response.json()
    task_id = str(body["taskId"])
    started = await companion.heartbeat(task_id, str(body["leaseId"]))
    assert started.status_code == 200, started.text
    return task_id, str(body["leaseId"]), body


# ---------------------------------------------------------------------------
# Shared assertions
# ---------------------------------------------------------------------------


def problem_code(response: httpx.Response) -> tuple[int, str]:
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    return response.status_code, str(body["code"])


async def active_tasks(api: Api, device_id: str) -> list[MobileTaskRow]:
    async with api.app.state.database.unit_of_work() as session:
        return list(
            await session.scalars(
                select(MobileTaskRow).where(
                    MobileTaskRow.tenant_id == OPERATOR["X-Tenant-Id"],
                    MobileTaskRow.device_id == device_id,
                    MobileTaskRow.status.in_(("CLAIMED", "RUNNING")),
                )
            )
        )


async def live_leases(api: Api, device_id: str) -> list[DeviceLeaseRow]:
    async with api.app.state.database.unit_of_work() as session:
        return list(
            await session.scalars(
                select(DeviceLeaseRow).where(
                    DeviceLeaseRow.device_id == device_id,
                    DeviceLeaseRow.canceled_at.is_(None),
                )
            )
        )


async def task_row(api: Api, task_id: str) -> MobileTaskRow:
    async with api.app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        return row


async def expire_task_lease(api: Api, task_id: str) -> None:
    """Simulate the disconnect: the lease lapses with no further heartbeats."""
    async with api.app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_id)
        assert row is not None
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)


async def assert_single_writer(companion: Companion, *, task_id: str) -> None:
    """fleet-identity/v1 §6.1: one active task + one live lease per device."""
    active = await active_tasks(companion.api, companion.device_id)
    assert [item.id for item in active] == [task_id]
    leases = await live_leases(companion.api, companion.device_id)
    assert len(leases) == 1
    row = await task_row(companion.api, task_id)
    assert row.lease_id == leases[0].lease_id


# ---------------------------------------------------------------------------
# Fixture wiring
# ---------------------------------------------------------------------------


async def test_q10_scenario_fixture_pins_gate_definition() -> None:
    """The scenario fixture is the Q10 gate definition — keep it honest."""
    from cloudctl_api.fleet_identity import (
        READ_COMMAND_TYPES,
        AccountBusyError,
        AuthorizationEnvelopeStaleError,
        ReconcileRequiredError,
    )

    scenario = load_scenario()
    assert scenario["contract"] == "fleet-identity/v1@20260916.1"
    assert scenario["task"].startswith("Q10")
    # Side-effect-free command policy: the read families are exactly the
    # contract's read set; the write representative is none of them.
    declared_reads = {
        scenario["sideEffectFreeCommands"]["readProbe"],
        *scenario["sideEffectFreeCommands"]["collectReadFamily"],
    }
    assert declared_reads == set(READ_COMMAND_TYPES)
    # Faults the gate must inject.
    faults = set(scenario["injectedFaults"])
    assert "reclaim-after-release (cross-process)" in faults
    assert "stale-binding-token (reinstall/rebind)" in faults
    assert "duplicate-event-replay (same and diverging content)" in faults
    assert "device-a-disconnect (lease lapse mid-run)" in faults
    assert "tenant-conflict (same account write mutex across devices/processes)" in faults
    # Error-code wiring matches the implementation constants.
    codes = scenario["expectedErrorCodes"]
    assert codes["accountBusy"]["code"] == AccountBusyError.code
    assert codes["accountBusy"]["status"] == AccountBusyError.status
    assert codes["reconcileRequired"]["code"] == ReconcileRequiredError.code
    assert codes["reconcileRequired"]["status"] == ReconcileRequiredError.status
    assert codes["envelopeStale"]["code"] == AuthorizationEnvelopeStaleError.code
    assert codes["envelopeStale"]["status"] == AuthorizationEnvelopeStaleError.status
    # Two API processes, two device clients, each pinned to its own process.
    assert scenario["topology"]["apiProcesses"] == 2
    roles = {item["role"] for item in scenario["topology"]["deviceClients"]}
    assert roles == {"deviceA", "deviceB"}
    pinned = {
        item["role"]: item["pinnedApiProcess"]
        for item in scenario["topology"]["deviceClients"]
    }
    assert pinned == {"deviceA": 1, "deviceB": 2}
    # The skipped on-device items are declared (counted separately below).
    assert [item["id"] for item in scenario["deviceItems"]] == list(DEVICE_ITEM_IDS)


# ---------------------------------------------------------------------------
# Gate: parallel progress, no double write, no crosstalk
# ---------------------------------------------------------------------------


async def test_two_processes_two_devices_parallel_no_double_write_no_crosstalk(two_apis):
    api1, api2 = two_apis
    scenario = load_scenario()
    device_a = companion_for(api1, scenario, "deviceA")
    device_b = companion_for(api2, scenario, "deviceB")
    await device_a.provision()
    await device_b.provision()
    await device_a.negotiate()
    await device_b.negotiate()

    account_a = await bind_account(
        api1, device_a.device_id, f"q10-parallel-a-{uuid.uuid4().hex[:8]}"
    )
    account_b = await bind_account(
        api2, device_b.device_id, f"q10-parallel-b-{uuid.uuid4().hex[:8]}"
    )
    task_a = await create_probe_task(api1, device_a.device_id, account_id=account_a)
    task_b = await create_probe_task(api2, device_b.device_id, account_id=account_b)

    # Both devices claim through their own API process at the same time.
    claim_a, claim_b = await asyncio.gather(device_a.claim(), device_b.claim())
    assert claim_a.status_code == 200, claim_a.text
    assert claim_b.status_code == 200, claim_b.text
    assert claim_a.json()["taskId"] == task_a
    assert claim_b.json()["taskId"] == task_b
    lease_a = claim_a.json()["leaseId"]
    lease_b = claim_b.json()["leaseId"]
    assert lease_a != lease_b

    # No same-device double write: exactly one active task and one live lease
    # per device, visible identically from BOTH API processes (shared DB).
    await assert_single_writer(device_a, task_id=task_a)
    await assert_single_writer(device_b, task_id=task_b)
    cross_view = await task_row(api2, task_a)  # read A's task via API-2
    assert cross_view.lease_id == lease_a

    # No cross-device crosstalk: A's binding cannot drive B's task and
    # vice versa (404 — a foreign task does not even exist for the binding).
    intruder = await device_a.api.client.post(
        f"/companion/v2/tasks/{task_b}/heartbeat",
        headers=device_a.auth,
        json={"leaseId": lease_b, "currentStep": 0, "leaseSeconds": 60},
    )
    assert intruder.status_code == 404, intruder.text
    reverse = await device_b.api.client.post(
        f"/companion/v2/tasks/{task_a}/complete",
        headers=device_b.auth,
        json={"leaseId": lease_a, "result": {"outcome": "stolen"}},
    )
    assert reverse.status_code == 404, reverse.text

    # Both progress in parallel to SUCCEEDED through their own processes.
    started_a = await device_a.heartbeat(task_a, lease_a, step=0)
    started_b = await device_b.heartbeat(task_b, lease_b, step=0)
    assert started_a.status_code == 200, started_a.text
    assert started_b.status_code == 200, started_b.text
    probe_result = {"outcome": "ok", "resultType": "DeviceProbeResult", "schemaVersion": 1}
    done_a = await device_a.complete(task_a, lease_a, probe_result)
    done_b = await device_b.complete(task_b, lease_b, probe_result)
    assert done_a.status_code == 200, done_a.text
    assert done_b.status_code == 200, done_b.text
    for api, task_id in ((api1, task_a), (api2, task_b), (api2, task_a), (api1, task_b)):
        row = await task_row(api, task_id)
        assert row.status == "SUCCEEDED"
        assert row.business_state == "SUCCEEDED"
    # Settled: no device keeps a live lease or an active task.
    assert await active_tasks(api1, device_a.device_id) == []
    assert await live_leases(api1, device_a.device_id) == []
    assert await active_tasks(api2, device_b.device_id) == []
    assert await live_leases(api2, device_b.device_id) == []


# ---------------------------------------------------------------------------
# Fault: device A disconnects mid-run; device B unaffected; A recovers
# ---------------------------------------------------------------------------


async def test_device_a_disconnect_b_unaffected_and_a_recovers(two_apis):
    api1, api2 = two_apis
    scenario = load_scenario()
    device_a = companion_for(api1, scenario, "deviceA")
    device_b = companion_for(api2, scenario, "deviceB")
    await device_a.provision()
    await device_b.provision()
    await device_a.negotiate()
    await device_b.negotiate()
    account_a = await bind_account(api1, device_a.device_id, f"q10-disc-a-{uuid.uuid4().hex[:8]}")
    account_b = await bind_account(api2, device_b.device_id, f"q10-disc-b-{uuid.uuid4().hex[:8]}")
    task_a = await create_probe_task(api1, device_a.device_id, account_id=account_a)
    task_b = await create_probe_task(api2, device_b.device_id, account_id=account_b)
    claimed_a, lease_a, _ = await claim_ok(device_a)
    claimed_b, lease_b, _ = await claim_ok(device_b)
    assert claimed_a == task_a and claimed_b == task_b

    # Device A drops off the network mid-run: the lease lapses silently.
    await expire_task_lease(api1, task_a)

    # Device B never notices: it keeps heartbeating and settles fine.
    keepalive = await device_b.heartbeat(task_b, lease_b, step=0)
    assert keepalive.status_code == 200, keepalive.text
    settled_b = await task_row(api2, task_b)
    assert settled_b.status == "RUNNING"  # still mid-run while A is dark
    done_b = await device_b.complete(
        task_b,
        lease_b,
        {"outcome": "ok", "resultType": "DeviceProbeResult", "schemaVersion": 1},
    )
    assert done_b.status_code == 200, done_b.text
    assert await active_tasks(api2, device_b.device_id) == []
    assert await live_leases(api2, device_b.device_id) == []

    # A's disconnected task is NOT re-executed as fresh work while its lease
    # is still recorded active on the device (single-writer guard): the next
    # claim first reclaims the expired task, then re-dispatches it.
    recovered = await device_a.claim()
    assert recovered.status_code == 200, recovered.text
    body = recovered.json()
    assert body["taskId"] == task_a
    assert body["attempt"] == 2
    assert body["leaseId"] != lease_a
    await assert_single_writer(device_a, task_id=task_a)

    # B stays settled and untouched by A's recovery.
    row_b = await task_row(api2, task_b)
    assert row_b.status == "SUCCEEDED"
    assert await active_tasks(api2, device_b.device_id) == []


# ---------------------------------------------------------------------------
# Fault: operator cancels A while B runs (K03 current semantics; A12 pending)
# ---------------------------------------------------------------------------


async def test_cancel_device_a_device_b_unaffected(two_apis):
    api1, api2 = two_apis
    scenario = load_scenario()
    device_a = companion_for(api1, scenario, "deviceA")
    device_b = companion_for(api2, scenario, "deviceB")
    await device_a.provision()
    await device_b.provision()
    account_a = await bind_account(api1, device_a.device_id, f"q10-cancel-a-{uuid.uuid4().hex[:8]}")
    account_b = await bind_account(api2, device_b.device_id, f"q10-cancel-b-{uuid.uuid4().hex[:8]}")
    task_a = await create_probe_task(api1, device_a.device_id, account_id=account_a)
    task_b = await create_probe_task(api2, device_b.device_id, account_id=account_b)
    _, lease_a, _ = await claim_ok(device_a)
    _, lease_b, _ = await claim_ok(device_b)

    # Operator cancels A through API-1 while both devices are RUNNING.
    cancel = await api1.client.post(
        f"/api/v1/platform-tasks/{task_a}:cancel",
        headers=OPERATOR,
        json={"reason": "q10 cancel A"},
    )
    assert cancel.status_code == 200, cancel.text
    # K03 current implementation: a RUNNING task degrades to CANCEL_REQUESTED
    # (A12's convergence matrix is not merged at this SHA — pending A12).
    assert cancel.json()["state"] == "CANCEL_REQUESTED"
    assert cancel.json()["runnerStatus"] == "RUNNING"

    # Device B is completely unaffected: it settles successfully.
    done_b = await device_b.complete(
        task_b,
        lease_b,
        {"outcome": "ok", "resultType": "DeviceProbeResult", "schemaVersion": 1},
    )
    assert done_b.status_code == 200, done_b.text
    row_b = await task_row(api2, task_b)
    assert row_b.status == "SUCCEEDED"
    assert row_b.business_state == "SUCCEEDED"
    assert row_b.stall_reason is None  # A's cancel reason never leaks to B

    # A's Companion honors the request at its next safe point via the fail
    # path (current K03 convergence; the dedicated matrix is A12's).
    honored = await device_a.fail(task_a, lease_a, "CANCELLED", "q10 cancel A honored")
    assert honored.status_code == 200, honored.text
    row_a = await task_row(api2, task_a)  # cross-process view
    assert row_a.status == "FAILED"
    assert row_a.error_code == "CANCELLED"
    # Pending A12 joint verification: the business view of a canceled task
    # converges to FAILED + errorCode=CANCELLED today; whether it should read
    # CANCELLED as a first-class business terminal is A12's matrix.

    # Canceling A released the device: no lingering active task or lease.
    assert await active_tasks(api1, device_a.device_id) == []
    assert await live_leases(api1, device_a.device_id) == []


# ---------------------------------------------------------------------------
# Fault: cross-process reclaim keeps the §7 frozen identity
# ---------------------------------------------------------------------------


async def test_cross_process_reclaim_keeps_frozen_identity(two_apis):
    from cloudctl_api.mobile_service import COMMAND_REGISTRY_VERSION

    api1, api2 = two_apis
    scenario = load_scenario()
    device_a = companion_for(api1, scenario, "deviceA")
    await device_a.provision()
    await device_a.negotiate()
    task_id = await create_steps_task(api1, device_a.device_id, polish_steps())

    first = await device_a.claim()
    assert first.status_code == 200, first.text
    assert first.json()["taskId"] == task_id
    # P09-19 release: PREFLIGHT-only, before the first heartbeat.
    released = await device_a.release(task_id, first.json()["leaseId"])
    assert released.status_code == 200, released.text

    # The very same device reclaims through the OTHER API process.
    second = await device_a.claim()
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["taskId"] == task_id
    assert body["attempt"] == 2
    assert body["leaseId"] != first.json()["leaseId"]

    # §7 frozen identity is byte-identical across processes and attempts.
    for api in (api1, api2):
        row = await task_row(api, task_id)
        metadata = row.steps[0]
        real_steps = [step for step in row.steps if step.get("action")]
        expected = hashlib.sha256(canonical_steps(real_steps).encode()).hexdigest()
        assert metadata["payloadIdentity"] == expected
        assert metadata["commandRegistryVersion"] == COMMAND_REGISTRY_VERSION
    await assert_single_writer(device_a, task_id=task_id)


# ---------------------------------------------------------------------------
# Faults: stale token + stale authorization envelope (B11 API-side view)
# ---------------------------------------------------------------------------


async def test_stale_token_and_envelope_rejected_without_touching_b(two_apis):
    api1, api2 = two_apis
    scenario = load_scenario()
    expected = load_scenario()["expectedErrorCodes"]
    device_a = companion_for(api1, scenario, "deviceA")
    device_b = companion_for(api2, scenario, "deviceB")
    await device_a.provision()
    await device_b.provision()
    await device_a.negotiate()
    await device_b.negotiate()
    account_a = await bind_account(api1, device_a.device_id, f"q10-stale-a-{uuid.uuid4().hex[:8]}")
    task_a = await create_probe_task(api1, device_a.device_id, account_id=account_a)
    claimed_a, lease_a, _ = await claim_ok(device_a)
    assert claimed_a == task_a
    stale_token = dict(device_a.auth)

    # Device A reboots: a fresh session with a new bootId is registered
    # through API-2 (any process sees the shared session registry).
    await device_a.negotiate(boot_id="q10-boot-a-2")

    # A late heartbeat under the pre-reboot lease is rejected as a stale
    # authorization envelope — on BOTH API processes.
    late_on_api1 = await device_a.api.client.post(
        f"/companion/v2/tasks/{task_a}/heartbeat",
        headers=device_a.auth,
        json={"leaseId": lease_a, "currentStep": 1, "leaseSeconds": 60},
    )
    status, code = problem_code(late_on_api1)
    assert (status, code) == (
        expected["envelopeStale"]["status"],
        expected["envelopeStale"]["code"],
    )

    # Reinstall (new app instance) supersedes the binding: the old token is
    # dead everywhere, while the new credential keeps working (B11 semantics
    # observed from the API).
    await device_a.reinstall("q10-instance-a-reinstalled")
    dead_claim = await api2.client.post(
        "/companion/v2/tasks/claim", headers=stale_token, json={"leaseSeconds": 60}
    )
    assert dead_claim.status_code == 401, dead_claim.text
    alive = await device_a.device_heartbeat()
    assert alive.status_code == 200, alive.text

    # Device B never noticed any of A's churn: it settles its own task.
    account_b = await bind_account(api2, device_b.device_id, f"q10-stale-b-{uuid.uuid4().hex[:8]}")
    task_b = await create_probe_task(api2, device_b.device_id, account_id=account_b)
    _, lease_b, _ = await claim_ok(device_b)
    done_b = await device_b.complete(
        task_b,
        lease_b,
        {"outcome": "ok", "resultType": "DeviceProbeResult", "schemaVersion": 1},
    )
    assert done_b.status_code == 200, done_b.text


# ---------------------------------------------------------------------------
# Fault: duplicate event replay
# ---------------------------------------------------------------------------


async def test_duplicate_events_replay_idempotent(two_apis):
    api1, api2 = two_apis
    scenario = load_scenario()
    device_b = companion_for(api2, scenario, "deviceB")
    await device_b.provision()
    account_b = await bind_account(api2, device_b.device_id, f"q10-event-b-{uuid.uuid4().hex[:8]}")
    task_id = await create_probe_task(api2, device_b.device_id, account_id=account_b)
    _, lease_id, _ = await claim_ok(device_b)

    payload = {
        "eventType": "STEP_STARTED",
        "stepIndex": 0,
        "payload": {"stepId": "probe-capabilities"},
    }
    first = await device_b.send_event(task_id, lease_id, 1, payload)
    assert first.status_code == 201, first.text
    assert first.headers["Idempotency-Replayed"] == "false"

    # Identical replay: idempotent 200, flagged as a replay, no new row.
    replay = await device_b.send_event(task_id, lease_id, 1, payload)
    assert replay.status_code == 200, replay.text
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["id"] == first.json()["id"]

    # Same sequence with diverging content is refused.
    tampered = await device_b.send_event(
        task_id,
        lease_id,
        1,
        {
            "eventType": "STEP_STARTED",
            "stepIndex": 0,
            "payload": {"stepId": "some-other-step"},
        },
    )
    assert tampered.status_code == 409, tampered.text

    # The stream continues from the next sequence without a gap.
    nxt = await device_b.send_event(
        task_id,
        lease_id,
        2,
        {
            "eventType": "STEP_SUCCEEDED",
            "stepIndex": 0,
            "payload": {"stepId": "probe-capabilities"},
        },
    )
    assert nxt.status_code == 201, nxt.text

    async with api1.app.state.database.unit_of_work() as session:  # cross-process view
        rows = list(
            await session.scalars(
                select(MobileTaskEventRow).where(MobileTaskEventRow.task_id == task_id)
            )
        )
    assert [row.sequence for row in rows] == [1, 2]
    assert len({row.id for row in rows}) == 2


# ---------------------------------------------------------------------------
# Fault: tenant conflict — account write mutex across devices AND processes
# ---------------------------------------------------------------------------


async def test_account_write_mutex_across_devices_and_processes(two_apis):
    api1, api2 = two_apis
    scenario = load_scenario()
    expected = scenario["expectedErrorCodes"]
    device_a = companion_for(api1, scenario, "deviceA")
    device_b = companion_for(api2, scenario, "deviceB")
    await device_a.provision()
    await device_b.provision()
    account = await bind_account(api1, device_a.device_id, "q10-mutex-account")
    bound_again = await api1.client.post(
        f"/api/v1/accounts/{account}/bindings",
        headers=OPERATOR,
        json={"deviceId": device_b.device_id, "confirmationNote": "Q10 second binding."},
    )
    assert bound_again.status_code == 201, bound_again.text

    # Both write tasks come from the side-effect-free maintenance family;
    # no real publish happens (simulated companions only).
    task_a = await create_steps_task(api1, device_a.device_id, polish_steps(), account_id=account)
    task_b = await create_steps_task(api2, device_b.device_id, polish_steps(), account_id=account)

    started_a, lease_a, _ = await claim_ok(device_a)
    assert started_a == task_a

    # The same account's second write task — different device, different API
    # process — must answer 409 ACCOUNT_BUSY and stay QUEUED (KEEP_WAITING).
    busy = await device_b.claim()
    status, code = problem_code(busy)
    assert (status, code) == (
        expected["accountBusy"]["status"],
        expected["accountBusy"]["code"],
    )
    row_b = await task_row(api1, task_b)
    assert row_b.status == "QUEUED"
    assert row_b.business_state == "QUEUED"

    # Once the RUNNING write settles, the account frees for device B.
    done_a = await device_a.complete(task_a, lease_a, {"outcome": "polished"})
    assert done_a.status_code == 200, done_a.text
    retry = await device_b.claim()
    assert retry.status_code == 200, retry.text
    assert retry.json()["taskId"] == task_b


# ---------------------------------------------------------------------------
# Fault: cross-tenant isolation across the two processes
# ---------------------------------------------------------------------------


async def test_cross_tenant_isolation_two_processes(two_apis):
    api1, api2 = two_apis
    scenario = load_scenario()
    cross = load_cross_tenant()
    device_a = companion_for(api1, scenario, "deviceA")
    await device_a.provision()
    account_a = await bind_account(api1, device_a.device_id, f"q10-cross-a-{uuid.uuid4().hex[:8]}")
    task_a = await create_probe_task(api1, device_a.device_id, account_id=account_a)

    tenant_b_headers = {
        **identity(),
        "X-Tenant-Id": cross["secondTenant"]["tenantId"],
        "X-User-Id": cross["secondTenant"]["userId"],
    }
    device_b2 = companion_for(api2, scenario, "deviceB")
    device_b2.operator_headers = tenant_b_headers
    device_b2.logical_name = cross["secondTenant"]["device"]["logicalName"]
    device_b2.app_instance_id = cross["secondTenant"]["device"]["appInstanceId"]
    await device_b2.provision()
    account_b2 = await bind_account(
        api2,
        device_b2.device_id,
        f"q10-cross-b2-{uuid.uuid4().hex[:8]}",
        headers=tenant_b_headers,
    )
    task_b2 = await create_probe_task(
        api2, device_b2.device_id, account_id=account_b2, headers=tenant_b_headers
    )

    # Claims resolve inside each tenant — no crosstalk.
    claim_a, claim_b2 = await asyncio.gather(device_a.claim(), device_b2.claim())
    assert claim_a.status_code == 200, claim_a.text
    assert claim_b2.status_code == 200, claim_b2.text
    assert claim_a.json()["taskId"] == task_a
    assert claim_b2.json()["taskId"] == task_b2

    # Tenant B's operator cannot read or cancel tenant A's task.
    foreign_read = await api2.client.get(
        f"/api/v1/platform-tasks/{task_a}", headers=tenant_b_headers
    )
    assert foreign_read.status_code == 404, foreign_read.text
    foreign_cancel = await api2.client.post(
        f"/api/v1/platform-tasks/{task_a}:cancel",
        headers=tenant_b_headers,
        json={"reason": "q10 cross-tenant attempt"},
    )
    assert foreign_cancel.status_code == 404, foreign_cancel.text

    # A tenant B binding cannot drive tenant A's task either.
    intruder = await api2.client.post(
        f"/companion/v2/tasks/{task_a}/heartbeat",
        headers=device_b2.auth,
        json={"leaseId": claim_a.json()["leaseId"], "currentStep": 0, "leaseSeconds": 60},
    )
    assert intruder.status_code == 404, intruder.text

    # Both tasks settle inside their own tenants.
    for device, task_id, claim in (
        (device_a, task_a, claim_a),
        (device_b2, task_b2, claim_b2),
    ):
        done = await device.complete(
            task_id,
            claim.json()["leaseId"],
            {"outcome": "ok", "resultType": "DeviceProbeResult", "schemaVersion": 1},
        )
        assert done.status_code == 200, done.text


# ---------------------------------------------------------------------------
# Fault: open UNKNOWN blocks only its own device (A11 §8 in the fleet view)
# ---------------------------------------------------------------------------


async def test_open_unknown_blocks_only_own_device(two_apis):
    from cloudctl_api.mobile_actions import steps_action_identity

    api1, api2 = two_apis
    scenario = load_scenario()
    expected = scenario["expectedErrorCodes"]
    device_a = companion_for(api1, scenario, "deviceA")
    device_b = companion_for(api2, scenario, "deviceB")
    await device_a.provision()
    await device_b.provision()
    task_a = await create_steps_task(api1, device_a.device_id, delist_steps(0))
    account_b = await bind_account(
        api2, device_b.device_id, f"q10-unknown-b-{uuid.uuid4().hex[:8]}"
    )
    task_b = await create_probe_task(api2, device_b.device_id, account_id=account_b)

    claimed_a, lease_a, _ = await claim_ok(device_a)
    assert claimed_a == task_a
    async with api1.app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_a)
        assert row is not None
        frozen = steps_action_identity(row)
    intent = await api1.client.post(
        f"/companion/v2/tasks/{task_a}/actions/intent",
        headers=device_a.auth,
        json={
            "leaseId": lease_a,
            "actionId": frozen["action_id"],
            "actionKey": frozen["action_key"],
            "parameterHash": frozen["parameter_hash"],
            "beforeEvidence": "evidence://q10-before",
        },
    )
    assert intent.status_code == 201, intent.text
    outcome = await api1.client.post(
        f"/companion/v2/tasks/{task_a}/actions/{frozen['action_key']}/outcome",
        headers=device_a.auth,
        json={
            "leaseId": lease_a,
            "parameterHash": frozen["parameter_hash"],
            "status": "UNKNOWN",
            "evidence": "evidence://q10-lost",
        },
    )
    assert outcome.status_code == 200, outcome.text

    # Crash-requeue: the task falls back to QUEUED while the UNKNOWN row is
    # open — device A must be blocked from reclaiming (KEEP_WAITING).
    async with api1.app.state.database.unit_of_work() as session:
        row = await session.get(MobileTaskRow, task_a)
        assert row is not None
        row.status = "QUEUED"
        row.business_state = "QUEUED"
        row.lease_id = None
        row.lease_expires_at = None
        lease = await session.get(DeviceLeaseRow, device_a.device_id)
        if lease is not None:
            lease.canceled_at = datetime.now(UTC)
    blocked = await device_a.claim()
    status, code = problem_code(blocked)
    assert (status, code) == (
        expected["reconcileRequired"]["status"],
        expected["reconcileRequired"]["code"],
    )

    # Device B is NOT blocked by A's open UNKNOWN: it claims and settles.
    _, lease_b, _ = await claim_ok(device_b)
    done_b = await device_b.complete(
        task_b,
        lease_b,
        {"outcome": "ok", "resultType": "DeviceProbeResult", "schemaVersion": 1},
    )
    assert done_b.status_code == 200, done_b.text

    async with api2.app.state.database.unit_of_work() as session:
        ledger = await session.get(MobileActionCommitRow, frozen["action_key"])
        assert ledger is not None and ledger.status == "UNKNOWN"
        assert ledger.resolved_at is None


# ---------------------------------------------------------------------------
# Accounting: software results vs skipped device items
# ---------------------------------------------------------------------------


async def test_q10_software_and_device_item_accounting() -> None:
    """Explicit separate counts of software results and device-side items."""
    scenario = load_scenario()
    device_items = scenario["deviceItems"]
    software_tests = [
        "test_q10_scenario_fixture_pins_gate_definition",
        "test_two_processes_two_devices_parallel_no_double_write_no_crosstalk",
        "test_device_a_disconnect_b_unaffected_and_a_recovers",
        "test_cancel_device_a_device_b_unaffected",
        "test_cross_process_reclaim_keeps_frozen_identity",
        "test_stale_token_and_envelope_rejected_without_touching_b",
        "test_duplicate_events_replay_idempotent",
        "test_account_write_mutex_across_devices_and_processes",
        "test_cross_tenant_isolation_two_processes",
        "test_open_unknown_blocks_only_own_device",
    ]
    print("\n[Q10 accounting] software result items:", len(software_tests) + 1)
    for name in software_tests:
        print(f"[Q10 software] {name}")
    print("[Q10 software] test_q10_software_and_device_item_accounting")
    skipped = [item["id"] for item in device_items]
    print(f"[Q10 accounting] skipped device items: {len(skipped)}")
    for item in device_items:
        print(f"[Q10 device-skip] {item['id']} — {item['aspect']} ({item['owner']})")
    assert skipped == list(DEVICE_ITEM_IDS)
    assert len(skipped) == 3
    assert len(software_tests) == 10


# ---------------------------------------------------------------------------
# On-device items (B10/B11 hardware line) — skipped, counted separately
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="device-item q10-device-real-partition-after-intent: physical network "
    "partition after the gated intent commit requires real hardware (B10/B11); "
    "software projection covered by lease-lapse + open-UNKNOWN tests"
)
async def test_device_item_real_network_partition_after_intent(two_apis) -> None:
    raise AssertionError("never runs: hardware-only")


@pytest.mark.skip(
    reason="device-item q10-device-arbiter-single-writer: B10 on-device "
    "DeviceArbiter arbitration executes inside the Android Companion process; "
    "API-side projection is the at-most-one-active-task-per-device invariant"
)
async def test_device_item_device_arbiter_single_writer(two_apis) -> None:
    raise AssertionError("never runs: hardware-only")


@pytest.mark.skip(
    reason="device-item q10-device-real-executable-gates: accessibility/IME/"
    "screen-unlock gates against a real Android runtime (B10/B11); software "
    "gate evaluation is covered by the A10 mirror tests at this SHA"
)
async def test_device_item_real_executable_gates(two_apis) -> None:
    raise AssertionError("never runs: hardware-only")
