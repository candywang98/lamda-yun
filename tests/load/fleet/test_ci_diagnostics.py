"""Diagnostic lifecycle tests; probe activation is always explicit."""

import asyncio
import inspect
import json
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import httpx
import pytest
from cloudctl_api.mobile_service import MobileTaskService
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import Pool

from . import ci_diagnostics, test_fleet_load
from .ci_diagnostics import PHASE, REQUEST, Probe, diagnose, summary
from .harness import FleetLoadApp, run_scenario


def test_import_has_no_instrumentation_side_effects() -> None:
    assert Pool.connect.__module__.startswith("sqlalchemy.")
    assert MobileTaskService.claim.__module__ == "cloudctl_api.mobile_service"
    assert httpx.AsyncClient.send.__module__ == "httpx._client"
    source = inspect.getsource(ci_diagnostics)
    assert "test_hundred_simulated_clients_control_plane_holds(basetemp)" in source
    assert "subprocess" not in source
    assert "os.environ" not in source


def test_summary_matches_repository_nearest_rank_percentile() -> None:
    assert summary([1.0, 2.0])["p95Seconds"] == 2.0
    assert summary([2.0, 1.0])["p50Seconds"] == 1.0
    assert summary([]) == {"count": 0}


@pytest.mark.parametrize("fails", [False, True])
async def test_async_wrapper_preserves_result_exception_and_context(fails: bool) -> None:
    marker = object()

    class Subject:
        async def call(self) -> object:
            if fails:
                raise LookupError("unit-test-marker")
            return marker

    original = Subject.call
    probe = Probe()
    with ExitStack() as stack:
        probe.wrap_async(stack, Subject, "call", "measured")
        if fails:
            with pytest.raises(LookupError, match="unit-test-marker"):
                await Subject().call()
        else:
            assert await Subject().call() is marker
        assert PHASE.get() == REQUEST.get() == "outside"
    assert Subject.call is original
    assert probe.calls["measured"] == 1
    assert len(probe.timings["outside:measured"]) == 1


@pytest.mark.parametrize("failure", ["assertion", "timeout", "cancel"])
async def test_observer_drains_and_hooks_restore_on_failure(failure: str) -> None:
    originals = (Pool.connect, MobileTaskService.claim, httpx.AsyncClient.send)
    probe = Probe()
    error: type[BaseException] = {
        "assertion": AssertionError,
        "timeout": TimeoutError,
        "cancel": asyncio.CancelledError,
    }[failure]
    with pytest.raises(error):
        async with probe.observe():
            if failure == "assertion":
                raise AssertionError("unit-test failure")
            if failure == "cancel":
                raise asyncio.CancelledError
            async with asyncio.timeout(0.01):
                await asyncio.sleep(10)
    assert probe.cleaned and probe.observer is not None and probe.observer.done()
    assert originals == (Pool.connect, MobileTaskService.claim, httpx.AsyncClient.send)
    assert not event.contains(Engine, "before_cursor_execute", probe.before)
    assert not event.contains(Engine, "after_cursor_execute", probe.after)
    assert not event.contains(Engine, "handle_error", probe.error)


async def test_partial_installation_failure_restores_patches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = Pool.connect
    probe = Probe()
    listen = event.listen

    def broken(target: Any, name: str, callback: Any) -> None:
        if name == "after_cursor_execute":
            raise RuntimeError("injected listener registration failure")
        listen(target, name, callback)

    monkeypatch.setattr(event, "listen", broken)
    with pytest.raises(RuntimeError, match="registration failure"):
        async with probe.observe():
            pytest.fail("must not enter partially installed probe")
    assert probe.cleaned and probe.observer is None
    assert Pool.connect is original
    assert not event.contains(Engine, "before_cursor_execute", probe.before)


async def test_cleanup_failure_is_not_reported_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = Probe()
    async with probe.observe():
        pass
    assert probe.cleaned
    original = Pool.connect
    remove = event.remove

    def broken(target: Any, name: str, callback: Any) -> None:
        if name == "after_cursor_execute":
            raise RuntimeError("injected removal failure")
        remove(target, name, callback)

    monkeypatch.setattr(event, "remove", broken)
    try:
        with pytest.raises(RuntimeError, match="removal failure"):
            async with probe.observe():
                pass
        assert not probe.cleaned
        assert probe.report(1, "RuntimeError")["cleanup"]["patchesAndListenersRemoved"] is False
        assert probe.observer is not None and probe.observer.done()
        assert Pool.connect is original
        assert event.contains(Engine, "after_cursor_execute", probe.after)
    finally:
        # Restore the deliberately failed test listener, never leak it into another test.
        remove(Engine, "after_cursor_execute", probe.after)


async def test_runner_cancellation_propagates_and_records_non_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    originals = (Pool.connect, MobileTaskService.claim, httpx.AsyncClient.send)

    async def canceled(path: Path) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(
        test_fleet_load, "test_hundred_simulated_clients_control_plane_holds", canceled
    )
    directory = tmp_path / "canceled"
    with pytest.raises(asyncio.CancelledError):
        await diagnose(directory)
    report = json.loads((directory / "diagnostic.json").read_text())
    assert report["exit"] == 1 and report["errorType"] == "CancelledError"
    assert report["cleanup"] == {"patchesAndListenersRemoved": True, "observerDone": True}
    assert originals == (Pool.connect, MobileTaskService.claim, httpx.AsyncClient.send)


@pytest.mark.parametrize("outcome", ["success", "assertion", "timeout"])
async def test_runner_records_honest_exit_and_refuses_directory_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    # Unit-test only the runner's exit/cleanup contract, not workload success.
    async def target(path: Path) -> None:
        assert await asyncio.to_thread(path.is_dir)
        if outcome == "assertion":
            raise AssertionError("unit-test failure")
        if outcome == "timeout":
            await asyncio.sleep(10)

    monkeypatch.setattr(
        test_fleet_load, "test_hundred_simulated_clients_control_plane_holds", target
    )
    directory = tmp_path / "diagnostic"
    deadline_seconds = 0.01 if outcome == "timeout" else ci_diagnostics.DEADLINE_SECONDS
    exit_code = await diagnose(directory, deadline_seconds=deadline_seconds)
    report = json.loads((directory / "diagnostic.json").read_text())
    assert exit_code == report["exit"] == (0 if outcome == "success" else 1)
    assert (
        report["errorType"]
        == {"success": None, "assertion": "AssertionError", "timeout": "TimeoutError"}[outcome]
    )
    assert report["cleanup"] == {"patchesAndListenersRemoved": True, "observerDone": True}
    original = (directory / "diagnostic.json").read_bytes()
    with pytest.raises(FileExistsError):
        await diagnose(directory)
    assert (directory / "diagnostic.json").read_bytes() == original


async def test_probe_real_asgi_postgres_and_sanitized_output(tmp_path: Path) -> None:
    probe = Probe()
    async with probe.observe():
        result = await run_scenario(device_count=1, tasks_per_device=1, report_dir=tmp_path)
    harness = result["harness"]
    assert harness.postgres.root is not None and not harness.postgres.root.exists()
    assert harness.app.state.database.engine.pool.checkedout() == 0
    assert sum(o.completed for o in result["outcomes"].values()) == 1
    assert all(not o.errors for o in result["outcomes"].values())
    report = probe.report(0, None)
    assert report["database"]["serverVersion"]
    assert report["database"]["pool"]["type"] == "AsyncAdaptedQueuePool"
    assert report["methodInvocations"]["claimService"] == 1
    assert all(report["methodInvocations"][key] == 0 for key in ci_diagnostics.CHANGED_METHODS)
    assert report["timings"]["eventLoopLag"]["count"] > 0
    assert report["timings"]["claim:authenticate:poolAcquireTotal"]["count"] > 0
    assert report["claimSql"]
    assert report["sqlErrors"] == 0
    serialized = json.dumps(report)
    for secret in ("Bearer", "bindingToken", "database_url", "token_digest", "parameters"):
        assert secret not in serialized
    assert report["cleanup"] == {"patchesAndListenersRemoved": True, "observerDone": True}


@pytest.mark.parametrize("error", [AssertionError, asyncio.CancelledError])
async def test_probe_failure_preserves_owned_postgres_cleanup(
    error: type[BaseException],
) -> None:
    probe = Probe()
    harness = FleetLoadApp()
    with pytest.raises(error, match="after PostgreSQL start"):
        async with probe.observe(), harness:
            raise error("after PostgreSQL start")
    assert harness.postgres.root is not None and not harness.postgres.root.exists()
    assert probe.observer is not None and probe.observer.done()
    assert probe.cleaned
