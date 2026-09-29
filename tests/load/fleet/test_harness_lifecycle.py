"""Worker shutdown must finish before its HTTP and database resources close."""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Any

import httpx
import pytest

from . import harness as fleet


def exception_leaves(error: BaseException) -> list[BaseException]:
    if isinstance(error, BaseExceptionGroup):
        return [leaf for child in error.exceptions for leaf in exception_leaves(child)]
    return [error]


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", ["worker-error", "outer-cancellation"])
async def test_workers_drain_before_harness_resources_close(
    monkeypatch: pytest.MonkeyPatch, stop: str
) -> None:
    original_post = httpx.AsyncClient.post
    original_exit = fleet.FleetLoadApp.__aexit__
    workers: set[asyncio.Task[Any]] = set()
    ready = asyncio.Event()
    fail_now = asyncio.Event()
    cancellation_started = asyncio.Event()
    release_cleanup = asyncio.Event()
    closing = asyncio.Event()
    drained_at_close: list[bool] = []
    client_open_during_cleanup: list[bool] = []
    closed_clients: list[bool] = []
    failure = RuntimeError("injected worker failure")

    async def held_claim(client: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        if url != "/companion/v2/tasks/claim":
            return await original_post(client, url, **kwargs)
        task = asyncio.current_task()
        assert task is not None
        workers.add(task)
        first = len(workers) == 1
        if len(workers) == 2:
            ready.set()
        try:
            if first and stop == "worker-error":
                await fail_now.wait()
                raise failure
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancellation_started.set()
            await release_cleanup.wait()
            client_open_during_cleanup.append(not client.is_closed)
            raise
        raise AssertionError("held claim unexpectedly resumed")

    async def observed_exit(
        harness: fleet.FleetLoadApp,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        drained_at_close.append(all(task.done() for task in workers))
        closing.set()
        await original_exit(harness, exc_type, exc, traceback)
        closed_clients.append(harness.client.is_closed)

    monkeypatch.setattr(httpx.AsyncClient, "post", held_claim)
    monkeypatch.setattr(fleet.FleetLoadApp, "__aexit__", observed_exit)
    run = asyncio.create_task(
        fleet.run_scenario(device_count=2, tasks_per_device=1, scenario_name="lifecycle")
    )
    signals = [
        asyncio.create_task(cancellation_started.wait()),
        asyncio.create_task(closing.wait()),
    ]
    caught: BaseException | None = None
    try:
        await asyncio.wait_for(ready.wait(), timeout=10)
        if stop == "worker-error":
            fail_now.set()
        else:
            run.cancel()
        done, _ = await asyncio.wait(signals, timeout=10, return_when=asyncio.FIRST_COMPLETED)
        assert done, "neither sibling cancellation nor harness shutdown started"
        release_cleanup.set()
        try:
            await asyncio.wait_for(run, timeout=10)
        except BaseException as error:
            caught = error
    finally:
        # Drain the frozen broken implementation too, without hiding its ordering failure.
        release_cleanup.set()
        for task in [run, *workers, *signals]:
            if not task.done():
                task.cancel()
        await asyncio.gather(run, *workers, *signals, return_exceptions=True)

    assert drained_at_close == [True], "harness resources closed before sibling workers drained"
    assert client_open_during_cleanup == [True] * (1 if stop == "worker-error" else 2)
    assert closed_clients == [True]
    assert all(task.done() for task in workers)
    assert caught is not None, "worker failure or caller cancellation must propagate"
    if stop == "worker-error":
        assert exception_leaves(caught) == [failure]
    else:
        assert isinstance(caught, asyncio.CancelledError)
