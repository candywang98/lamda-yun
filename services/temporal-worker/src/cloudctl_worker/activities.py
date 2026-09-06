"""Temporal activities. All database, network, and Edge I/O lives here."""

from __future__ import annotations

from cloudctl_observability import bind_context
from temporalio import activity

from .backend import ActivityBackend
from .contracts import CommitIntent, Lease, PublishTargetInput, ReconcileObservation


class PublishActivities:
    def __init__(self, backend: ActivityBackend) -> None:
        self.backend = backend

    @activity.defn
    async def validate_snapshot(self, input: PublishTargetInput) -> None:
        with bind_context(tenant_id=input.tenant_id, target_id=input.target_id):
            await self.backend.validate_snapshot(input)

    @activity.defn
    async def acquire_device_lease(self, input: PublishTargetInput, workflow_id: str) -> Lease:
        with bind_context(
            tenant_id=input.tenant_id,
            workflow_id=workflow_id,
            target_id=input.target_id,
            device_id=input.device_id,
        ):
            return await self.backend.acquire_lease(input, workflow_id)

    @activity.defn
    async def edge_preflight(self, input: PublishTargetInput, lease: Lease) -> None:
        with bind_context(tenant_id=input.tenant_id, target_id=input.target_id):
            await self.backend.preflight(input, lease)

    @activity.defn
    async def stage_media(self, input: PublishTargetInput, lease: Lease) -> None:
        with bind_context(tenant_id=input.tenant_id, target_id=input.target_id):
            await self.backend.stage_media(input, lease)

    @activity.defn
    async def run_prepare_steps(self, input: PublishTargetInput, lease: Lease) -> str:
        with bind_context(tenant_id=input.tenant_id, target_id=input.target_id):
            return await self.backend.prepare(input, lease)

    @activity.defn
    async def write_commit_intent(
        self,
        input: PublishTargetInput,
        lease: Lease,
        before_commit_evidence_id: str,
    ) -> CommitIntent:
        with bind_context(tenant_id=input.tenant_id, target_id=input.target_id):
            return await self.backend.write_commit_intent(input, lease, before_commit_evidence_id)

    @activity.defn
    async def commit_once(
        self, input: PublishTargetInput, lease: Lease, intent: CommitIntent
    ) -> None:
        with bind_context(tenant_id=input.tenant_id, target_id=input.target_id):
            await self.backend.commit_once(input, lease, intent)

    @activity.defn
    async def reconcile_result(
        self, input: PublishTargetInput, lease: Lease
    ) -> ReconcileObservation:
        with bind_context(tenant_id=input.tenant_id, target_id=input.target_id):
            return await self.backend.reconcile(input, lease)

    @activity.defn
    async def mark_target_state(
        self, input: PublishTargetInput, state: str, detail: str | None
    ) -> None:
        with bind_context(tenant_id=input.tenant_id, target_id=input.target_id):
            await self.backend.mark_state(input, state, detail)

    @activity.defn
    async def cleanup(self, input: PublishTargetInput, lease: Lease | None) -> None:
        with bind_context(tenant_id=input.tenant_id, target_id=input.target_id):
            await self.backend.cleanup(input, lease)

    @activity.defn
    async def release_device_lease(self, input: PublishTargetInput, lease: Lease) -> None:
        with bind_context(tenant_id=input.tenant_id, target_id=input.target_id):
            await self.backend.release_lease(input, lease)
