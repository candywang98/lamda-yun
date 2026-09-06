from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from cloudctl_edge_protocol import edge_control_pb2 as pb

from .spool import EdgeSpool, StaleFencingToken


class RunnerBusy(RuntimeError):
    pass


class HardwareBlockedError(RuntimeError):
    """A real-device step cannot start because authorized hardware is unavailable."""


EventSink = Callable[[pb.TaskEvent], Awaitable[None]]


class RunnerExecutor(Protocol):
    async def execute(
        self,
        command: pb.StartCommand,
        cancel_event: asyncio.Event,
        event_sink: EventSink,
    ) -> None: ...


@dataclass(slots=True)
class _Runner:
    command: pb.StartCommand
    cancel_event: asyncio.Event
    task: asyncio.Task[None]


class RunnerSupervisor:
    """Enforces one active runner per device and rechecks the fence before device access."""

    def __init__(self, spool: EdgeSpool, executor: RunnerExecutor, event_sink: EventSink):
        self._spool = spool
        self._executor = executor
        self._event_sink = event_sink
        self._active: dict[str, _Runner] = {}
        self._lock = asyncio.Lock()

    async def start(self, command: pb.StartCommand) -> None:
        async with self._lock:
            current = self._active.get(command.device_id)
            if current is not None and not current.task.done():
                raise RunnerBusy(f"device {command.device_id} already has an active runner")
            cancel_event = asyncio.Event()
            task = asyncio.create_task(
                self._run(command, cancel_event), name=f"runner:{command.device_id}"
            )
            self._active[command.device_id] = _Runner(command, cancel_event, task)

    async def cancel(self, command_id: str) -> bool:
        async with self._lock:
            for runner in self._active.values():
                if runner.command.command_id == command_id and not runner.task.done():
                    runner.cancel_event.set()
                    return True
        return False

    async def wait(self, device_id: str) -> None:
        async with self._lock:
            runner = self._active.get(device_id)
        if runner is not None:
            await runner.task

    def active_command(self, device_id: str) -> str | None:
        runner = self._active.get(device_id)
        if runner is None or runner.task.done():
            return None
        return runner.command.command_id

    def cancel_stale(self, device_id: str, current_fencing_token: int) -> None:
        runner = self._active.get(device_id)
        if (
            runner is not None
            and not runner.task.done()
            and runner.command.fencing_token < current_fencing_token
        ):
            runner.cancel_event.set()

    async def _run(self, command: pb.StartCommand, cancel_event: asyncio.Event) -> None:
        state = "FAILED"
        try:
            self._spool.assert_current_fence(
                command.device_id, command.lease_id, command.fencing_token
            )
            self._spool.set_command_state(command.command_id, "STARTED")
            await self._event_sink(
                pb.TaskEvent(
                    command_id=command.command_id,
                    task_run_id=command.task_run_id,
                    step="runner",
                    state="STARTED",
                )
            )
            await self._executor.execute(command, cancel_event, self._event_sink)
            state = "CANCELED" if cancel_event.is_set() else "SUCCEEDED"
        except asyncio.CancelledError:
            cancel_event.set()
            state = "CANCELED"
            raise
        except HardwareBlockedError:
            state = "BLOCKED_HARDWARE"
        except StaleFencingToken:
            state = "CANCELED" if cancel_event.is_set() else "FAILED"
        except Exception:
            state = "FAILED"
        finally:
            try:
                self._spool.set_command_state(command.command_id, state)
                await self._event_sink(
                    pb.TaskEvent(
                        command_id=command.command_id,
                        task_run_id=command.task_run_id,
                        step="runner",
                        state=state,
                    )
                )
            finally:
                async with self._lock:
                    current = self._active.get(command.device_id)
                    if current is not None and current.command.command_id == command.command_id:
                        self._active.pop(command.device_id, None)
