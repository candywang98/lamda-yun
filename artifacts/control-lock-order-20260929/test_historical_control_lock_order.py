"""Frozen 7d58f6b characterization, NOT permanent desired behavior or a CI gate."""

from __future__ import annotations

import pytest
from test_fleet_control_lock_order import (
    SCENARIOS,
    Api,
    control_apis,  # noqa: F401 - pytest fixture
    control_postgres,  # noqa: F401 - pytest fixture
    exercise,
)


@pytest.mark.parametrize("scenario", SCENARIOS)
async def test_historical_inversion_yields_postgres_deadlock(
    control_apis: tuple[Api, Api],  # noqa: F811 - imported pytest fixture
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    report = await exercise(control_apis, monkeypatch, scenario)
    assert report["wait_edge"] is not None
    assert len(set(report["pids"].values())) == 2
    assert len(report["errors"]) == 1
    assert report["errors"][0]["sqlstate"] == "40P01"
    assert sorted(result["status"] for result in report["http"].values()) == [200, 500]
    first, second = (
        ("cancel", "claim") if scenario == "queued_cancel" else ("heartbeat", "take_control")
    )
    barrier = next(
        index for index, entry in enumerate(report["trace"]) if entry["phase"] == "barrier_released"
    )
    held = report["trace"][:barrier]
    assert any(
        entry["role"] == first
        and entry["phase"] == "completed"
        and "FROM mobile_task " in entry["sql"]
        and "FOR UPDATE" in entry["sql"]
        for entry in held
    )
    assert any(
        entry["role"] == second
        and entry["phase"] == "completed"
        and "FROM device_lease " in entry["sql"]
        and "FOR UPDATE" in entry["sql"]
        for entry in held
    )
    assert report["wait_edge"]["pid"] == report["pids"][second]
    assert report["pids"][first] in report["wait_edge"]["blockers"]
    assert report["wait_edge"]["wait_event_type"] == "Lock"
    if scenario == "queued_cancel":
        assert report["after"]["tasks"][0] == report["before"]["tasks"][0]
        task = report["after"]["tasks"][1]
        lease = report["after"]["lease"]
        if report["http"]["cancel"]["status"] == 200:
            assert (task["status"], task["businessState"]) == ("FAILED", "CANCELLED")
            assert lease == report["before"]["lease"]
        else:
            assert (task["status"], task["businessState"]) == ("CLAIMED", "PREFLIGHT")
            assert lease["id"] == task["leaseId"] and lease["canceledAt"] is None
    else:
        task = report["after"]["tasks"][0]
        if report["http"]["take_control"]["status"] == 200:
            assert task["businessState"] == "PAUSED_WAITING_USER"
            assert report["after"]["lease"]["owner"] == report["liveState"] == "REMOTE"
        else:
            assert task["businessState"] == "RUNNING"
            assert report["after"]["lease"]["owner"] == "AUTO"
            assert report["liveState"] == "VIEWING"
