"""Replay-safe workflows. No system time, random, file, database, or network I/O."""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from .activities import PublishActivities
    from .contracts import (
        Lease,
        PublishPlanInput,
        PublishPlanOutcome,
        PublishTargetInput,
        TargetOutcome,
    )


READ_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=15),
    maximum_attempts=5,
)
IDEMPOTENT_WRITE_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=8,
)
COMMIT_ONCE_RETRY = RetryPolicy(maximum_attempts=1)


@workflow.defn
class PublishTargetWorkflow:
    def __init__(self) -> None:
        self._approved = False
        self._cancel_requested = False
        self._phase = "CREATED"

    @workflow.signal
    async def approve_commit(self) -> None:
        self._approved = True

    @workflow.signal
    async def request_cancel(self) -> None:
        self._cancel_requested = True

    @workflow.query
    def phase(self) -> str:
        return self._phase

    @workflow.run
    async def run(self, input: PublishTargetInput) -> TargetOutcome:
        lease: Lease | None = None
        commit_intent_written = False
        try:
            self._phase = "VALIDATING"
            await workflow.execute_activity_method(
                PublishActivities.validate_snapshot,
                input,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=READ_RETRY,
            )
            if self._cancel_requested:
                return await self._cancel_at_safe_point(input)

            self._phase = "ACQUIRING_LEASE"
            await self._mark(input, "QUEUED", None)
            lease = await workflow.execute_activity_method(
                PublishActivities.acquire_device_lease,
                args=[input, workflow.info().workflow_id],
                start_to_close_timeout=timedelta(seconds=20),
                retry_policy=IDEMPOTENT_WRITE_RETRY,
            )
            await self._mark(input, "RUNNING", None)

            self._phase = "PREFLIGHT"
            await workflow.execute_activity_method(
                PublishActivities.edge_preflight,
                args=[input, lease],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=READ_RETRY,
            )
            if self._cancel_requested:
                return await self._cancel_at_safe_point(input)

            self._phase = "PREPARING"
            await workflow.execute_activity_method(
                PublishActivities.stage_media,
                args=[input, lease],
                start_to_close_timeout=timedelta(minutes=5),
                heartbeat_timeout=timedelta(seconds=30),
                retry_policy=IDEMPOTENT_WRITE_RETRY,
            )
            before_commit_evidence_id = await workflow.execute_activity_method(
                PublishActivities.run_prepare_steps,
                args=[input, lease],
                start_to_close_timeout=timedelta(minutes=10),
                heartbeat_timeout=timedelta(seconds=30),
                retry_policy=READ_RETRY,
            )
            if self._cancel_requested:
                return await self._cancel_at_safe_point(input)

            if input.requires_human_confirmation:
                self._phase = "WAITING_CONFIRMATION"
                await self._mark(input, "WAITING_CONFIRMATION", None)
                await workflow.wait_condition(lambda: self._approved or self._cancel_requested)
                if self._cancel_requested:
                    return await self._cancel_at_safe_point(input)

            self._phase = "WRITING_COMMIT_INTENT"
            intent = await workflow.execute_activity_method(
                PublishActivities.write_commit_intent,
                args=[input, lease, before_commit_evidence_id],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=IDEMPOTENT_WRITE_RETRY,
            )
            commit_intent_written = True

            self._phase = "COMMITTING"
            commit_detail: str | None = None
            try:
                await workflow.execute_activity_method(
                    PublishActivities.commit_once,
                    args=[input, lease, intent],
                    start_to_close_timeout=timedelta(seconds=90),
                    heartbeat_timeout=timedelta(seconds=20),
                    retry_policy=COMMIT_ONCE_RETRY,
                )
            except ActivityError:
                commit_detail = "commit transport result is uncertain; reconciling without retry"

            self._phase = "RECONCILING"
            await self._mark(input, "RECONCILING", commit_detail)
            observation = await workflow.execute_activity_method(
                PublishActivities.reconcile_result,
                args=[input, lease],
                start_to_close_timeout=timedelta(minutes=3),
                heartbeat_timeout=timedelta(seconds=30),
                retry_policy=READ_RETRY,
            )
            state = observation.state if observation.state in {"SUCCEEDED", "FAILED"} else "UNKNOWN"
            detail = observation.detail or commit_detail
            await self._mark(input, state, detail)
            self._phase = state
            return TargetOutcome(
                target_id=input.target_id,
                state=state,
                detail=detail,
                evidence_ids=observation.evidence_ids,
            )
        except ActivityError as exc:
            state = "UNKNOWN" if commit_intent_written else "FAILED"
            detail = (
                "activity failed after commit intent; manual reconciliation required"
                if commit_intent_written
                else f"activity failed before commit: {type(exc).__name__}"
            )
            await self._mark(input, state, detail)
            self._phase = state
            return TargetOutcome(target_id=input.target_id, state=state, detail=detail)
        finally:
            self._phase = (
                "CLEANUP"
                if self._phase not in {"SUCCEEDED", "FAILED", "UNKNOWN", "CANCELED"}
                else self._phase
            )
            await workflow.execute_activity_method(
                PublishActivities.cleanup,
                args=[input, lease],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=IDEMPOTENT_WRITE_RETRY,
            )
            if lease is not None:
                await workflow.execute_activity_method(
                    PublishActivities.release_device_lease,
                    args=[input, lease],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=IDEMPOTENT_WRITE_RETRY,
                )

    async def _mark(self, input: PublishTargetInput, state: str, detail: str | None) -> None:
        await workflow.execute_activity_method(
            PublishActivities.mark_target_state,
            args=[input, state, detail],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=IDEMPOTENT_WRITE_RETRY,
        )

    async def _cancel_at_safe_point(self, input: PublishTargetInput) -> TargetOutcome:
        await self._mark(input, "CANCELED", "canceled at a pre-commit safe point")
        self._phase = "CANCELED"
        return TargetOutcome(
            target_id=input.target_id,
            state="CANCELED",
            detail="canceled at a pre-commit safe point",
        )


@workflow.defn
class PublishPlanWorkflow:
    @workflow.run
    async def run(self, input: PublishPlanInput) -> PublishPlanOutcome:
        results: list[TargetOutcome] = []
        for index, target in enumerate(input.targets):
            result = await workflow.execute_child_workflow(
                PublishTargetWorkflow.run,
                target,
                id=f"publish-target/{target.target_id}",
            )
            results.append(result)
            if index and index % input.page_size == 0:
                await workflow.sleep(timedelta(milliseconds=1))
        return PublishPlanOutcome(plan_id=input.plan_id, targets=tuple(results))
