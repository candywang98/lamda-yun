"""Explicit post-failure diagnostic, never a replacement for the pytest gate."""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import functools
import json
import os
import platform
import re
import time
from collections import Counter, defaultdict
from collections.abc import AsyncIterator, Iterator
from contextlib import ExitStack, asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

import httpx
import sqlalchemy
from cloudctl_observability.metrics import percentile
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import Pool

REQUEST: contextvars.ContextVar[str] = contextvars.ContextVar("fleet_request", default="outside")
PHASE: contextvars.ContextVar[str] = contextvars.ContextVar("fleet_phase", default="outside")
TARGET = "tests.load.fleet.test_fleet_load.test_hundred_simulated_clients_control_plane_holds"
DEADLINE_SECONDS = 180
CHANGED_METHODS = ("changed_cancel", "changed_resume", "changed_take_control")


def summary(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0}
    return {
        "count": len(values),
        "sumSeconds": sum(values),
        "p50Seconds": percentile(values, 0.50),
        "p95Seconds": percentile(values, 0.95),
        "maxSeconds": ordered[-1],
    }


class Probe:
    def __init__(self) -> None:
        self.timings: dict[str, list[float]] = defaultdict(list)
        self.calls: Counter[str] = Counter(dict.fromkeys(CHANGED_METHODS, 0))
        self.sql: Counter[str] = Counter()
        self.sql_seconds: dict[str, float] = defaultdict(float)
        self.sql_errors = 0
        self.pool: dict[str, Any] = {}
        self.pg_version: list[int] | None = None
        self.observer: asyncio.Task[None] | None = None
        self.cleaned = False

    def patch(self, stack: ExitStack, owner: Any, name: str, value: Any) -> None:
        original = getattr(owner, name)
        stack.callback(setattr, owner, name, original)
        setattr(owner, name, value)

    def wrap_async(self, stack: ExitStack, owner: Any, name: str, label: str) -> None:
        original = getattr(owner, name)

        @functools.wraps(original)
        async def measured(*args: Any, **kwargs: Any) -> Any:
            self.calls[label] += 1
            token = PHASE.set(label)
            started = time.perf_counter()
            try:
                return await original(*args, **kwargs)
            finally:
                self.timings[f"{REQUEST.get()}:{label}"].append(time.perf_counter() - started)
                PHASE.reset(token)

        self.patch(stack, owner, name, measured)

    def before(
        self, conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
    ) -> None:
        if conn.dialect.name == "postgresql" and conn.dialect.server_version_info:
            self.pg_version = list(conn.dialect.server_version_info)
        if REQUEST.get() != "claim":
            return
        # Fixed operation/table labels only: never retain SQL values or parameters.
        sql = " ".join(statement.split())
        table = re.search(r"\b(?:FROM|UPDATE|INTO)\s+([a-z_]+)", sql, re.I)
        category = sql.split()[0] + ":" + (table.group(1) if table else "other")
        if "FOR UPDATE" in sql:
            category += ":FOR_UPDATE"
        context._fleet_diagnostic = (time.perf_counter(), PHASE.get() + ":" + category)

    def after(
        self, conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
    ) -> None:
        measured = getattr(context, "_fleet_diagnostic", None)
        if measured is not None:
            started, category = measured
            self.sql[category] += 1
            self.sql_seconds[category] += time.perf_counter() - started

    def error(self, context: Any) -> None:
        self.sql_errors += 1

    async def sample_loop(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            expected = loop.time() + 0.05
            await asyncio.sleep(0.05)
            self.timings["eventLoopLag"].append(max(0.0, loop.time() - expected))

    @contextmanager
    def restoration(self) -> Iterator[ExitStack]:
        stack = ExitStack()
        try:
            yield stack
        finally:
            # ExitStack still attempts all callbacks if one fails. Do not
            # report complete restoration unless the entire close succeeded.
            stack.close()
            self.cleaned = True

    @asynccontextmanager
    async def observe(self) -> AsyncIterator[None]:
        self.cleaned = False
        from cloudctl_api.db import Database
        from cloudctl_api.fleet_live import FleetLiveService
        from cloudctl_api.mobile_service import MobileTaskService
        from cloudctl_api.platform_tasks import PlatformTaskService

        try:
            with self.restoration() as stack:
                for owner, name, label in (
                    (MobileTaskService, "authenticate", "authenticate"),
                    (MobileTaskService, "claim", "claimService"),
                    (PlatformTaskService, "cancel", "changed_cancel"),
                    (PlatformTaskService, "resume", "changed_resume"),
                    (FleetLiveService, "take_control", "changed_take_control"),
                ):
                    self.wrap_async(stack, owner, name, label)
                original_send = httpx.AsyncClient.send

                async def send(client: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
                    kind = "claim" if request.url.path == "/companion/v2/tasks/claim" else "other"
                    token = REQUEST.set(kind)
                    started = time.perf_counter()
                    try:
                        return await original_send(client, request, *args, **kwargs)
                    finally:
                        self.timings[f"http:{kind}"].append(time.perf_counter() - started)
                        REQUEST.reset(token)

                self.patch(stack, httpx.AsyncClient, "send", send)
                original_connect = Pool.connect

                def connect(pool: Any) -> Any:
                    started = time.perf_counter()
                    try:
                        return original_connect(pool)
                    finally:
                        key = f"{REQUEST.get()}:{PHASE.get()}:poolAcquireTotal"
                        self.timings[key].append(time.perf_counter() - started)

                self.patch(stack, Pool, "connect", connect)
                original_init = Database.__init__

                def init(database: Any, *args: Any, **kwargs: Any) -> None:
                    original_init(database, *args, **kwargs)
                    pool = database.engine.pool
                    self.pool = {
                        "type": type(pool).__name__,
                        "size": pool.size(),
                        "maxOverflow": pool._max_overflow,
                        "timeoutSeconds": pool.timeout(),
                        "prePing": pool._pre_ping,
                    }

                self.patch(stack, Database, "__init__", init)
                for name, listener in (
                    ("before_cursor_execute", self.before),
                    ("after_cursor_execute", self.after),
                    ("handle_error", self.error),
                ):
                    event.listen(Engine, name, listener)
                    stack.callback(event.remove, Engine, name, listener)
                self.observer = asyncio.create_task(self.sample_loop(), name="fleet-ci-loop-lag")
                try:
                    yield
                finally:
                    self.observer.cancel()
                    try:
                        await self.observer
                    except asyncio.CancelledError:
                        pass
        finally:
            if self.observer is not None and not self.observer.done():
                self.cleaned = False

    def report(self, exit_code: int, error_type: str | None) -> dict[str, Any]:
        return {
            "diagnosticOnlyNotAcceptance": True,
            "target": TARGET,
            "exit": exit_code,
            "errorType": error_type,
            "host": {
                "system": platform.platform(),
                "machine": platform.machine(),
                "cpuCount": os.cpu_count(),
                "python": platform.python_version(),
            },
            "database": {
                "engine": "test-owned-loopback-postgresql",
                "driver": "asyncpg",
                "serverVersion": self.pg_version,
                "sqlalchemy": sqlalchemy.__version__,
                "pool": self.pool,
            },
            "methodInvocations": dict(self.calls),
            "timings": {key: summary(values) for key, values in self.timings.items()},
            "claimSql": {
                key: {"count": count, "elapsedSeconds": self.sql_seconds[key]}
                for key, count in self.sql.items()
            },
            "sqlErrors": self.sql_errors,
            "cleanup": {
                "patchesAndListenersRemoved": self.cleaned,
                "observerDone": self.observer is None or self.observer.done(),
            },
            "limits": [
                "Instrumented local ASGI simulation, not acceptance or causal proof.",
                "Pool.connect total includes acquisition, connection creation, pre-ping and hooks;"
                " not queue-only waiting. SQLAlchemy 2.0.52 implementation reviewed.",
                "SQL cursor counts exclude implicit protocol, pre-ping and commit/rollback.",
                "Wall intervals overlap across clients; SQL time excludes pool acquisition.",
                "Loop lag is sampled every 50 ms across the whole diagnostic, including setup.",
            ],
        }


async def diagnose(basetemp: Path, deadline_seconds: float = DEADLINE_SECONDS) -> int:
    from .test_fleet_load import test_hundred_simulated_clients_control_plane_holds

    # Refuse to erase or reuse a gate report directory.
    await asyncio.to_thread(basetemp.mkdir, parents=True, exist_ok=False)
    probe = Probe()
    code, error_type = 0, None
    try:
        async with probe.observe(), asyncio.timeout(deadline_seconds):
            await test_hundred_simulated_clients_control_plane_holds(basetemp)
    except BaseException as exc:
        code, error_type = 1, type(exc).__name__
        if not isinstance(exc, Exception):
            raise
    finally:
        await asyncio.to_thread(
            (basetemp / "diagnostic.json").write_text,
            json.dumps(probe.report(code, error_type), indent=2) + "\n",
            encoding="utf-8",
        )
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--basetemp", type=Path, required=True)
    args = parser.parse_args()
    return asyncio.run(diagnose(args.basetemp))


if __name__ == "__main__":
    raise SystemExit(main())
