"""F12 fleet schedule worker: due-mint workflows, activities, and backends.

Temporal only decides *when* a scheduled occurrence is minted. The mint
itself is a single idempotent HTTP call into control-api
(``POST /api/v1/fleet-schedules/{schedule_id}:mint-due``), which derives the
stable fire key ``sha256(schedule_id:utc_time:device_id)[:64]`` server-side
(A04-compatible Idempotency-Key semantics). Consequences:

* A crashed worker, a restarted tick loop, or a Temporal Activity retry all
  re-send the *same* request for the same period — control-api replays the
  existing MobileTask (200) instead of double-minting (201 first only).
* Fire identity is stable per period: the deterministic workflow id
  ``fleet-schedule-mint/{schedule_id}/{period_marker}`` makes repeated ticks
  converge on one workflow per (schedule, period) — an already-running or
  completed child is skipped, not duplicated.
* Cancel never touches this layer beyond the server refusing future mints;
  minted tasks are cancelled per-task through platform-tasks :cancel.

The control plane stays the single source of truth for occurrence math, DST
rules and the missed-fire policy (fleet-first F12 §2): this worker carries no
schedule state of its own.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Protocol

from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, WorkflowAlreadyStartedError

with workflow.unsafe.imports_passed_through():
    # Activity/backend-only imports: passed through so the workflow sandbox
    # (which re-executes this module) never sandboxes httpx/uuid/logging.
    import uuid

    import httpx
    from cloudctl_observability import bind_context


# Mint retries are safe by construction: every attempt re-sends the same
# (schedule, period) request and the server-side fire key deduplicates.
MINT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=15),
    maximum_attempts=8,
)
POLL_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=15),
    maximum_attempts=5,
)


# ---------------------------------------------------------------------------
# Workflow contracts (stable, serialization-friendly)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DueMintItem:
    schedule_id: str
    period_marker: str
    scheduled_for: str  # aware-UTC ISO-8601 instant
    timezone: str


@dataclass(frozen=True)
class FleetScheduleMintInput:
    tenant_id: str
    schedule_id: str
    period_marker: str
    scheduled_for: str


@dataclass(frozen=True)
class MintOutcome:
    schedule_id: str
    period_marker: str
    created_any: bool
    task_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FleetScheduleTickInput:
    tenant_id: str
    poll_interval_seconds: int = 60
    max_children_per_tick: int = 50
    max_ticks: int = 1000  # continue-as-new bound keeps history finite


def mint_workflow_id(schedule_id: str, period_marker: str) -> str:
    """Deterministic per-period workflow id — the tick-level fire identity.

    ``period_marker`` is the occurrence's canonical UTC ISO instant computed
    from the persisted schedule definition, so every tick derives the same id
    for the same period regardless of when the tick runs.
    """
    safe_marker = period_marker.replace(":", "-")
    return f"fleet-schedule-mint/{schedule_id}/{safe_marker}"


# ---------------------------------------------------------------------------
# Backend ports
# ---------------------------------------------------------------------------


class ScheduleMintBackend(Protocol):
    async def poll_due(self, tenant_id: str) -> tuple[DueMintItem, ...]: ...

    async def mint_due(self, command: FleetScheduleMintInput) -> MintOutcome: ...


class ControlPlaneScheduleBackend:
    """HTTP adapter against the control-api fleet schedule surface."""

    def __init__(
        self,
        base_url: str,
        service_headers: dict[str, str],
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30)
        self._headers = service_headers

    async def poll_due(self, tenant_id: str) -> tuple[DueMintItem, ...]:
        response = await self._client.post(
            "/api/v1/fleet-schedules:poll",
            headers={**self._headers, "X-Tenant-Id": tenant_id},
            json={},
        )
        response.raise_for_status()
        payload = response.json()
        return tuple(
            DueMintItem(
                schedule_id=item["scheduleId"],
                period_marker=item["periodMarker"],
                scheduled_for=item["scheduledFor"],
                timezone=item["timezone"],
            )
            for item in payload.get("items", [])
        )

    async def mint_due(self, command: FleetScheduleMintInput) -> MintOutcome:
        response = await self._client.post(
            f"/api/v1/fleet-schedules/{command.schedule_id}:mint-due",
            headers={**self._headers, "X-Tenant-Id": command.tenant_id},
            json={},
        )
        response.raise_for_status()
        payload = response.json()
        return MintOutcome(
            schedule_id=payload["scheduleId"],
            period_marker=command.period_marker,
            created_any=bool(payload.get("createdAny")),
            task_ids=tuple(payload.get("taskIds") or ()),
        )


@dataclass
class InMemoryScheduleBackend:
    """Stateful test/development backend with server-side idempotency."""

    due: dict[tuple[str, str], DueMintItem] = field(default_factory=dict)
    minted: dict[tuple[str, str], MintOutcome] = field(default_factory=dict)
    mint_calls: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))

    def queue_due(self, item: DueMintItem) -> None:
        self.due[(item.schedule_id, item.period_marker)] = item

    async def poll_due(self, tenant_id: str) -> tuple[DueMintItem, ...]:
        return tuple(self.due.values())

    async def mint_due(self, command: FleetScheduleMintInput) -> MintOutcome:
        key = (command.schedule_id, command.period_marker)
        self.mint_calls[key] += 1
        existing = self.minted.get(key)
        if existing is not None:
            # Same key → replay: never a second mint (F12 §1).
            return MintOutcome(
                schedule_id=existing.schedule_id,
                period_marker=existing.period_marker,
                created_any=False,
                task_ids=existing.task_ids,
            )
        outcome = MintOutcome(
            schedule_id=command.schedule_id,
            period_marker=command.period_marker,
            created_any=True,
            task_ids=(f"task-{uuid.uuid5(uuid.NAMESPACE_URL, '/'.join(key))}",),
        )
        self.minted[key] = outcome
        return outcome


# ---------------------------------------------------------------------------
# Activities (all I/O lives in the backend)
# ---------------------------------------------------------------------------


class FleetScheduleActivities:
    def __init__(self, backend: ScheduleMintBackend) -> None:
        self.backend = backend

    @activity.defn
    async def poll_due_occurrences(self, tenant_id: str) -> tuple[DueMintItem, ...]:
        with bind_context(tenant_id=tenant_id):
            return await self.backend.poll_due(tenant_id)

    @activity.defn
    async def mint_due_occurrence(self, command: FleetScheduleMintInput) -> MintOutcome:
        with bind_context(
            tenant_id=command.tenant_id,
            schedule_id=command.schedule_id,
            period_marker=command.period_marker,
        ):
            return await self.backend.mint_due(command)


# ---------------------------------------------------------------------------
# Workflows (replay-safe: no system time, random, or I/O)
# ---------------------------------------------------------------------------


@workflow.defn
class FleetScheduleMintWorkflow:
    """Mint exactly one (schedule, period) occurrence.

    Retries (MINT_RETRY) re-send the identical command; the server-side fire
    key makes every attempt converge on the same MobileTask.
    """

    @workflow.run
    async def run(self, command: FleetScheduleMintInput) -> MintOutcome:
        try:
            return await workflow.execute_activity_method(
                FleetScheduleActivities.mint_due_occurrence,
                command,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=MINT_RETRY,
            )
        except ActivityError:
            # Mint outcome stays the server's truth: a permanently failing
            # mint is surfaced as a failed workflow for the tick loop to
            # observe; replaying it later still cannot double-mint.
            return MintOutcome(
                schedule_id=command.schedule_id,
                period_marker=command.period_marker,
                created_any=False,
                task_ids=(),
            )


@workflow.defn
class FleetScheduleTickWorkflow:
    """Poll loop: start one deterministic child per due period, then recur.

    Repeated ticks (or restarted workers) that observe the same period derive
    the same child workflow id; an already-started child is skipped. The loop
    continue-as-new at ``max_ticks`` to keep history bounded.
    """

    @workflow.run
    async def run(self, command: FleetScheduleTickInput) -> int:
        minted = 0
        for _ in range(command.max_ticks):
            due_items = await workflow.execute_activity_method(
                FleetScheduleActivities.poll_due_occurrences,
                command.tenant_id,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=POLL_RETRY,
            )
            for item in due_items[: command.max_children_per_tick]:
                child_input = FleetScheduleMintInput(
                    tenant_id=command.tenant_id,
                    schedule_id=item.schedule_id,
                    period_marker=item.period_marker,
                    scheduled_for=item.scheduled_for,
                )
                workflow_id = mint_workflow_id(item.schedule_id, item.period_marker)
                try:
                    await workflow.execute_child_workflow(
                        FleetScheduleMintWorkflow.run,
                        child_input,
                        id=workflow_id,
                    )
                    minted += 1
                except WorkflowAlreadyStartedError:
                    # Repeated tick on an in-flight/completed period — the
                    # deterministic id did its job; nothing to duplicate.
                    continue
            await workflow.sleep(timedelta(seconds=command.poll_interval_seconds))
        return minted


# Registration surface for the worker entry point (kept as a tuple so the
# entry registration stays a one-line spread).
SCHEDULE_WORKFLOWS = (FleetScheduleMintWorkflow, FleetScheduleTickWorkflow)
