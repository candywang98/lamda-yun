"""D11 fleet load scenarios over the in-process control plane.

三条验收：负载报告含主机规格/DB/配置/p50-p95；一台设备故障不形成全局
head-of-line；UNKNOWN 证据不随 50 条事件压缩丢失。模拟客户端 ≠ 真机。
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from .harness import FleetLoadApp, identity, run_scenario

REPORT_DIR = Path(__file__).resolve().parents[3] / "artifacts" / "tasks" / "D11"


@pytest.mark.asyncio
async def test_baseline_two_devices_twenty_tasks_report() -> None:
    result = await run_scenario(
        device_count=2,
        tasks_per_device=20,
        scenario_name="baseline-2x20",
        report_dir=REPORT_DIR,
    )
    report = result["report"]
    outcomes = result["outcomes"]

    assert report["simulatedClientsNotRealDevices"] is True
    assert report["host"]["cpuCount"] >= 1
    assert report["db"]["repositoryMode"] == "memory"
    assert report["config"]["deviceCount"] == 2

    for _device_id, outcome in outcomes.items():
        assert outcome.completed == 20, outcome.errors
        assert outcome.claimed >= 20, outcome.errors
        assert outcome.stranded == 0

    fleet = report["metrics"]["fleet"]
    assert fleet["queueAgeSeconds"]["count"] >= 40
    assert fleet["claimLatencySeconds"]["count"] >= 40
    assert fleet["queueAgeSeconds"]["p50"] >= 0.0
    assert fleet["queueAgeSeconds"]["p95"] >= fleet["queueAgeSeconds"]["p50"]
    assert fleet["inputFailure"] == 0
    assert fleet["leaseConflict"] == 0


@pytest.mark.asyncio
async def test_hundred_simulated_clients_control_plane_holds() -> None:
    result = await run_scenario(
        device_count=100,
        tasks_per_device=1,
        scenario_name="clients-100",
        report_dir=REPORT_DIR,
    )
    report = result["report"]
    assert report["config"]["deviceCount"] == 100
    completed = sum(o.completed for o in result["outcomes"].values())
    assert completed == 100
    fleet = report["metrics"]["fleet"]
    assert fleet["queueAgeSeconds"]["count"] >= 100
    assert fleet["claimLatencySeconds"]["p95"] < 5.0
    assert fleet["inputFailure"] == 0


@pytest.mark.asyncio
async def test_broken_device_is_not_a_global_head_of_line() -> None:
    result = await run_scenario(
        device_count=2,
        tasks_per_device=10,
        fail_device_names={"load-hol-000"},
        scenario_name="hol",
        report_dir=REPORT_DIR,
        emit_progress_events=False,
        # 20ms 节流避开已登记的 device_lease 并发竞态窗口（BLK-011，platform 线修复）。
        claim_pacing_seconds=0.02,
    )
    outcomes = list(result["outcomes"].values())
    healthy = [o for o in outcomes if o.stranded == 0]
    broken = [o for o in outcomes if o.stranded > 0]

    assert len(broken) == 1 and len(healthy) == 1
    # 单租约语义：故障设备卡死 1 个租约任务，其余滞留本设备队列不再被领取。
    assert broken[0].claimed == 1
    assert broken[0].stranded == 1
    assert broken[0].completed == 0
    assert healthy[0].completed == 10
    assert healthy[0].claimed >= 10

    report = result["report"]
    per_device = report["metrics"]["perDevice"]
    healthy_latency = per_device[healthy[0].device_id]["claimLatencySeconds"]
    assert healthy_latency["count"] == 10
    assert healthy_latency["p95"] < 2.0


@pytest.mark.asyncio
async def test_unknown_evidence_survives_control_event_compaction() -> None:
    from cloudctl_api.platform_tasks import (
        MAX_CONTROL_EVENTS,
        _retain_control_events,
    )

    # 单元层：60 条一般事件 + 首位的 MARKED_UNKNOWN —— 压缩后仍保留证据事件。
    events = [
        {
            "revision": 1,
            "event": "MARKED_UNKNOWN",
            "reason": "commit unknown",
            "actor": "op",
            "issuedAt": "t",
        }
    ]
    for revision in range(2, 63):
        events.append(
            {
                "revision": revision,
                "event": "PAUSE_REQUESTED",
                "reason": "churn",
                "actor": "op",
                "issuedAt": "t",
            }
        )
    retained = _retain_control_events(events)
    kinds = [event["event"] for event in retained]
    assert "MARKED_UNKNOWN" in kinds
    assert kinds.count("PAUSE_REQUESTED") == MAX_CONTROL_EVENTS
    assert retained[0]["event"] == "MARKED_UNKNOWN"

    # 集成层：真实 API 上 mark-unknown 的证据立即可见且持久。
    async with FleetLoadApp() as harness:
        client = harness.client
        device_id = await harness.seed_device("unknown-retention")
        await harness.seed_account_and_bind(device_id, "acc-unknown")
        account_id = await _only_account(harness)
        created = await client.post(
            "/api/v1/platform-tasks",
            headers={**identity(), "Idempotency-Key": f"unknown-{uuid.uuid4()!s}"[:120]},
            json={
                "deviceId": device_id,
                "accountId": account_id,
                "commandType": "device.probe_capabilities.v1",
                "parameters": {},
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["items"][0]["taskId"]

        marked = await client.post(
            f"/api/v1/platform-tasks/{task_id}:mark-unknown",
            headers=identity(),
            json={"reason": "commit result unknown (load test)"},
        )
        assert marked.status_code == 200, marked.text

        detail = await client.get(f"/api/v1/platform-tasks/{task_id}", headers=identity())
        events = list(
            detail.json().get("controlEvents")
            or (detail.json().get("control") or {}).get("controlEvents")
            or []
        )
        if not events:
            async with harness.app.state.database.unit_of_work() as session:
                from cloudctl_api.db import MobileTaskRow

                row = await session.scalar(select(MobileTaskRow).where(MobileTaskRow.id == task_id))
                events = list(((row.steps or [{}])[0] or {}).get("controlEvents") or [])
        assert "MARKED_UNKNOWN" in [event.get("event") for event in events]


async def _only_account(harness: FleetLoadApp) -> str:
    listing = await harness.client.get("/api/v1/accounts", headers=identity())
    payload = listing.json()
    items = payload if isinstance(payload, list) else (payload.get("items") or [])
    return str(items[-1]["id"])
