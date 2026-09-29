"""D11 fleet load harness: in-process simulated companions over ASGI.

在真实 ASGI 应用上跑模拟 companion（enroll→claim→event/heartbeat→complete），
用 observability.DeviceFleetMetrics 记录每设备 queueAge/claimLatency/冲突/
UNKNOWN/输入失败/证据上传，并产出含主机规格与测试配置的 JSON 负载报告。
模拟客户端 ≠ 真机：报告显式标注。
"""

from __future__ import annotations

import asyncio
import json
import os
import platform as host_platform
import time
import uuid
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

import httpx
from cloudctl_api import create_app
from cloudctl_api.db import Database, DeviceLeaseRow, MobileTaskRow
from cloudctl_api.settings import Settings
from cloudctl_observability import DeviceFleetMetrics
from fastapi import FastAPI
from sqlalchemy import select

from .postgres import FleetPostgres

TENANT = "00000000-0000-7000-8000-000000000111"
OPERATOR = "00000000-0000-7000-8000-000000000222"
PROBE_COMMAND = {"commandType": "device.probe_capabilities.v1", "parameters": {}}


def identity(role: str = "device_operator") -> dict[str, str]:
    return {
        "X-Tenant-Id": TENANT,
        "X-User-Id": OPERATOR,
        "X-Roles": role,
        "X-MFA": "true",
        "X-Request-Id": str(uuid.uuid4()),
    }


@dataclass
class WorkerOutcome:
    device_id: str
    claimed: int = 0
    completed: int = 0
    released: int = 0
    stranded: int = 0
    reclaimed: int = 0
    errors: list[str] = field(default_factory=list)
    claim_attempts: int = 0
    guard_exhausted: bool = False
    exit_reason: str = ""
    http_status_counts: dict[str, int] = field(default_factory=dict)
    completed_task_ids: list[str] = field(default_factory=list)
    stranded_task_ids: list[str] = field(default_factory=list)
    remaining_task_ids: list[str] = field(default_factory=list)
    task_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    device_lease: dict[str, Any] | None = None

    def record_response(self, operation: str, response: httpx.Response, expected: set[int]) -> None:
        key = f"{operation}-{response.status_code}"
        self.http_status_counts[key] = self.http_status_counts.get(key, 0) + 1
        if response.status_code not in expected:
            error = f"{key}:{response.text[:200]}"
            if error not in self.errors:
                self.errors.append(error)


class FleetLoadApp:
    def __init__(self) -> None:
        self.app: FastAPI
        self.client: httpx.AsyncClient
        self.postgres: FleetPostgres
        self._stack = AsyncExitStack()
        self.metrics = DeviceFleetMetrics()

    async def __aenter__(self) -> FleetLoadApp:
        await self._stack.__aenter__()
        try:
            self.postgres = self._stack.enter_context(FleetPostgres())
            self.app = create_app(
                Settings(
                    env="test",
                    repository_mode="postgresql",
                    database_url=self.postgres.database_url,
                    object_store_mode="memory",
                    dev_auth_bypass=True,
                )
            )
            database: Database = self.app.state.database
            try:
                await database.create_schema()
                await self._stack.enter_async_context(self.app.router.lifespan_context(self.app))
            except BaseException:
                # Lifespan owns disposal only once its entry has succeeded.
                await database.dispose()
                raise
            self.client = await self._stack.enter_async_context(
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=self.app), base_url="http://load"
                )
            )
            return self
        except BaseException:
            await self._stack.aclose()
            raise

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._stack.__aexit__(exc_type, exc, traceback)

    async def seed_device(self, name: str) -> str:
        response = await self.client.post(
            "/api/v1/mobile/devices",
            headers=identity(),
            json={
                "logicalName": name,
                "androidVersion": "14",
                "companionVersion": "1.0.0",
            },
        )
        response.raise_for_status()
        return str(response.json()["id"])

    async def seed_account_and_bind(self, device_id: str, subject: str) -> tuple[int, str]:
        account = await self.client.post(
            "/api/v1/accounts",
            headers=identity(),
            json={
                "platform": "xianyu",
                "externalSubjectRef": subject,
                "displayLabel": subject,
                "secretRef": f"vault://cloudctl/load/{subject}",
                "authorizationBasis": "Owner authorized the load test.",
            },
        )
        account.raise_for_status()
        account_id = str(account.json()["id"])
        bound = await self.client.post(
            f"/api/v1/accounts/{account_id}/bindings",
            headers=identity(),
            json={"deviceId": device_id, "confirmationNote": "Owner confirmed."},
        )
        bound.raise_for_status()
        return int(bound.json()["bindingVersion"]), account_id

    async def enroll(self, device_id: str, instance: str) -> dict[str, str]:
        code = await self.client.post(
            "/api/v1/mobile/enrollments",
            headers=identity(),
            json={"deviceId": device_id, "ttlSeconds": 900},
        )
        code.raise_for_status()
        token = await self.client.post(
            "/companion/v2/enroll",
            json={
                "code": code.json()["code"],
                "appInstanceId": instance,
                "companionVersion": "1.0.0",
            },
        )
        token.raise_for_status()
        return {"Authorization": f"Bearer {token.json()['bindingToken']}"}

    async def mint_probe(
        self, device_id: str, account_id: str, binding_version: int, key: str
    ) -> tuple[str, float]:
        minted_at = time.perf_counter()
        response = await self.client.post(
            "/api/v1/platform-tasks",
            headers={**identity(), "Idempotency-Key": key},
            json={
                "deviceId": device_id,
                "accountId": account_id,
                "expectedBindingVersion": binding_version,
                **PROBE_COMMAND,
            },
        )
        if response.status_code == 422:
            self.metrics.incr(device_id, "inputFailure")
            raise RuntimeError(f"mint rejected: {response.text}")
        response.raise_for_status()
        return str(response.json()["items"][0]["taskId"]), minted_at

    async def reconcile_outcome(
        self, outcome: WorkerOutcome, task_ids: list[str], *, intentional_failure: bool
    ) -> None:
        """Compare client acknowledgements with durable state after all workers stop."""
        database: Database = self.app.state.database
        async with database.unit_of_work() as session:
            rows = {
                row.id: row
                for row in await session.scalars(
                    select(MobileTaskRow).where(
                        MobileTaskRow.tenant_id == TENANT, MobileTaskRow.id.in_(task_ids)
                    )
                )
            }
            for task_id in task_ids:
                row = rows.get(task_id)
                outcome.task_states[task_id] = (
                    {
                        "status": row.status,
                        "businessState": row.business_state,
                        "deviceId": row.device_id,
                        "attempt": row.attempt,
                        "lastSequence": row.last_sequence,
                        "leaseId": row.lease_id,
                        "leaseExpiresAt": row.lease_expires_at.isoformat()
                        if row.lease_expires_at
                        else None,
                        "errorCode": row.error_code,
                    }
                    if row is not None
                    else {"status": "MISSING"}
                )
            lease = await session.get(DeviceLeaseRow, outcome.device_id)
            if lease is not None:
                outcome.device_lease = {
                    "leaseId": lease.lease_id,
                    "ownerWorkflowId": lease.owner_workflow_id,
                    "fencingToken": lease.fencing_token,
                    "expiresAt": lease.expires_at.isoformat(),
                    "canceledAt": lease.canceled_at.isoformat() if lease.canceled_at else None,
                }
        for task_id in task_ids:
            state = outcome.task_states[task_id]
            if state.get("deviceId") != outcome.device_id:
                outcome.errors.append(f"missing-or-wrong-device-task:{task_id}:{state}")
            elif task_id in outcome.completed_task_ids and (
                state["status"] != "SUCCEEDED" or state["businessState"] != "SUCCEEDED"
            ):
                outcome.errors.append(f"completion-not-persisted:{task_id}:{state}")

        expected_stall = (
            intentional_failure
            and outcome.stranded == 1
            and outcome.completed == 0
            and not outcome.errors
            and all(
                outcome.task_states[task_id]["status"]
                == ("RUNNING" if task_id in outcome.stranded_task_ids else "QUEUED")
                for task_id in task_ids
            )
        )
        if expected_stall:
            outcome.exit_reason = "intentional-device-failure"
        elif outcome.remaining_task_ids:
            outcome.exit_reason = "guard-exhausted" if outcome.guard_exhausted else "incomplete"
            outcome.errors.append(
                f"{outcome.exit_reason}:remaining={len(outcome.remaining_task_ids)};"
                f"claimAttempts={outcome.claim_attempts};"
                f"httpStatuses={json.dumps(outcome.http_status_counts, sort_keys=True)};"
                f"taskStates={json.dumps(outcome.task_states, sort_keys=True)}"
            )
        else:
            outcome.exit_reason = "failed" if outcome.errors else "completed"


async def run_scenario(
    *,
    device_count: int,
    tasks_per_device: int,
    fail_device_names: set[str] | None = None,
    report_dir: Path | None = None,
    scenario_name: str = "scenario",
    emit_progress_events: bool = True,
    claim_pacing_seconds: float = 0.0,
) -> dict[str, Any]:
    """Drive `device_count` simulated companions; failing devices strand tasks."""
    fail_device_names = fail_device_names or set()
    async with FleetLoadApp() as harness:
        started = time.perf_counter()
        devices: list[dict[str, Any]] = []
        for index in range(device_count):
            name = f"load-{scenario_name}-{index:03d}"
            device_id = await harness.seed_device(name)
            binding_version, account_id = await harness.seed_account_and_bind(
                device_id, f"acc-{index:03d}"
            )
            auth = await harness.enroll(device_id, f"instance-{index:03d}")
            devices.append(
                {
                    "name": name,
                    "id": device_id,
                    "accountId": account_id,
                    "bindingVersion": binding_version,
                    "auth": auth,
                    "fail": name in fail_device_names,
                }
            )

        minted: dict[str, list[tuple[str, float]]] = {}
        for device in devices:
            entries = []
            for seq in range(tasks_per_device):
                task_id, at = await harness.mint_probe(
                    device["id"],
                    device["accountId"],
                    device["bindingVersion"],
                    f"{scenario_name}-{devices.index(device):03d}-{seq:03d}",
                )
                entries.append((task_id, at))
            minted[device["id"]] = entries

        outcomes: dict[str, WorkerOutcome] = {
            device["id"]: WorkerOutcome(device_id=device["id"]) for device in devices
        }

        async def worker(device: dict[str, Any]) -> None:
            outcome = outcomes[device["id"]]
            mint_at = {task_id: at for task_id, at in minted[device["id"]]}
            remaining = set(mint_at)
            guard = tasks_per_device * 30 + 50
            while remaining and guard > 0:
                guard -= 1
                outcome.claim_attempts += 1
                if claim_pacing_seconds:
                    await asyncio.sleep(claim_pacing_seconds)
                claim_started = time.perf_counter()
                claim = await harness.client.post(
                    "/companion/v2/tasks/claim",
                    headers=device["auth"],
                    json={"leaseSeconds": 60},
                )
                claim_latency = time.perf_counter() - claim_started
                outcome.record_response("claim", claim, {200, 204})
                if claim.status_code == 204:
                    await asyncio.sleep(0.005)
                    continue
                if claim.status_code == 409:
                    harness.metrics.incr(device["id"], "leaseConflict")
                    await asyncio.sleep(0.005)
                    continue
                if claim.status_code == 422:
                    harness.metrics.incr(device["id"], "inputFailure")
                    await asyncio.sleep(0.005)
                    continue
                if claim.status_code >= 500:
                    # Preserve the error; a 5xx alone does not establish lease contention.
                    await asyncio.sleep(0.01)
                    continue
                claim.raise_for_status()
                body = claim.json()
                task_id = str(body["taskId"])
                if task_id not in remaining:
                    # 服务器重发了未清点的任务（如租约归还）；记录但不重复计量。
                    outcome.reclaimed += 1
                    outcome.errors.append(f"unexpected-claim:{task_id}")
                    await asyncio.sleep(0.005)
                    continue
                harness.metrics.observe(device["id"], "claimLatencySeconds", claim_latency)
                harness.metrics.observe(
                    device["id"], "queueAgeSeconds", time.perf_counter() - mint_at[task_id]
                )
                outcome.claimed += 1
                if device["fail"]:
                    # 故障设备：领取后不完成，只心跳一次然后放弃（任务滞留）。
                    heartbeat = await harness.client.post(
                        f"/companion/v2/tasks/{task_id}/heartbeat",
                        headers=device["auth"],
                        json={"leaseId": body["leaseId"]},
                    )
                    outcome.record_response("heartbeat", heartbeat, {200})
                    if heartbeat.status_code != 200:
                        break
                    outcome.stranded += 1
                    outcome.stranded_task_ids.append(task_id)
                    remaining.discard(task_id)
                    continue
                if emit_progress_events:
                    event = await harness.client.post(
                        f"/companion/v2/tasks/{task_id}/events",
                        headers=device["auth"],
                        json={
                            "leaseId": body["leaseId"],
                            "sequence": 1,
                            "eventType": "STEP_STARTED",
                            "stepIndex": 0,
                            "payload": {"note": "load"},
                        },
                    )
                    outcome.record_response("event", event, {201})
                    if event.status_code == 201:
                        harness.metrics.incr(device["id"], "evidenceUploads")
                complete = await harness.client.post(
                    f"/companion/v2/tasks/{task_id}/complete",
                    headers=device["auth"],
                    json={
                        "leaseId": body["leaseId"],
                        "result": {
                            "outcome": "ok",
                            "resultType": "DeviceProbeResult",
                            "schemaVersion": 1,
                        },
                    },
                )
                outcome.record_response("complete", complete, {200})
                if complete.status_code != 200:
                    # 瞬时冲突（租约/检查点竞态）退避后重试一次。
                    await asyncio.sleep(0.02)
                    complete = await harness.client.post(
                        f"/companion/v2/tasks/{task_id}/complete",
                        headers=device["auth"],
                        json={
                            "leaseId": body["leaseId"],
                            "result": {
                                "outcome": "ok",
                                "resultType": "DeviceProbeResult",
                                "schemaVersion": 1,
                            },
                        },
                    )
                    outcome.record_response("complete", complete, {200})
                if complete.status_code == 200:
                    outcome.completed += 1
                    outcome.completed_task_ids.append(task_id)
                    remaining.discard(task_id)
                else:
                    # Completion failure is evidence, not an accessibility-release reason.
                    harness.metrics.incr(device["id"], "inputFailure")
                    break
            outcome.remaining_task_ids = sorted(remaining)
            outcome.guard_exhausted = bool(remaining) and guard == 0

        async with asyncio.TaskGroup() as workers:
            for device in devices:
                workers.create_task(worker(device), name=f"fleet-worker:{device['id']}")
        for device in devices:
            await harness.reconcile_outcome(
                outcomes[device["id"]],
                [task_id for task_id, _ in minted[device["id"]]],
                intentional_failure=device["fail"],
            )
        duration = time.perf_counter() - started
        snapshot = harness.metrics.snapshot()
        report = {
            "scenario": scenario_name,
            "generatedAt": datetime.now(UTC).isoformat(),
            "simulatedClientsNotRealDevices": True,
            "host": {
                "machine": host_platform.machine(),
                "python": host_platform.python_version(),
                "system": host_platform.platform(),
                "cpuCount": os.cpu_count(),
            },
            "db": {
                "repositoryMode": "postgresql",
                "engine": "temporary-postgresql",
                "driver": harness.app.state.database.engine.dialect.driver,
                "serverVersion": list(
                    harness.app.state.database.engine.dialect.server_version_info
                ),
                "pool": type(harness.app.state.database.engine.pool).__name__,
            },
            "config": {
                "deviceCount": device_count,
                "tasksPerDevice": tasks_per_device,
                "failDevices": sorted(fail_device_names),
                "claimLeaseSeconds": 60,
            },
            "durationSeconds": round(duration, 3),
            "metrics": snapshot,
            "outcomes": {
                device_id: {
                    "claimed": o.claimed,
                    "completed": o.completed,
                    "stranded": o.stranded,
                    "released": o.released,
                    "reclaimed": o.reclaimed,
                    "errors": o.errors,
                    "expected": tasks_per_device,
                    "remaining": len(o.remaining_task_ids),
                    "remainingTaskIds": o.remaining_task_ids,
                    "completedTaskIds": o.completed_task_ids,
                    "strandedTaskIds": o.stranded_task_ids,
                    "claimAttempts": o.claim_attempts,
                    "guardExhausted": o.guard_exhausted,
                    "exitReason": o.exit_reason,
                    "httpStatusCounts": o.http_status_counts,
                    "taskStates": o.task_states,
                    "deviceLease": o.device_lease,
                }
                for device_id, o in outcomes.items()
            },
            "limits": (
                "in-process ASGI simulated clients; test-owned loopback PostgreSQL; "
                "not hardware, networked multi-node, or production-capacity evidence"
            ),
        }
        if report_dir is not None:
            await asyncio.to_thread(report_dir.mkdir, parents=True, exist_ok=True)
            payload = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
            await asyncio.to_thread(
                (report_dir / f"load-report-{scenario_name}.json").write_text,
                payload,
                "utf-8",
            )
        return {"report": report, "harness": harness, "outcomes": outcomes}
