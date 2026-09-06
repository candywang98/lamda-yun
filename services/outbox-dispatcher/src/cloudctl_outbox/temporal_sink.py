"""Start publish workflows from durable outbox events."""

from __future__ import annotations

from typing import Any, Protocol

import httpx
from cloudctl_worker.contracts import PublishPlanInput, PublishTargetInput
from cloudctl_worker.workflows import PublishPlanWorkflow
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.exceptions import WorkflowAlreadyStartedError

from .sinks import EventEnvelope


class PlanLoader(Protocol):
    async def load(self, tenant_id: str, plan_id: str) -> PublishPlanInput: ...


class AccessTokenProvider(Protocol):
    async def access_token(self) -> str: ...


class StaticAccessTokenProvider:
    def __init__(self, token: str) -> None:
        self.token = token

    async def access_token(self) -> str:
        return self.token


class ControlApiPlanLoader:
    def __init__(
        self,
        base_url: str,
        token_provider: AccessTokenProvider,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.client = client or httpx.AsyncClient(base_url=base_url, timeout=30)
        self.token_provider = token_provider

    async def load(self, tenant_id: str, plan_id: str) -> PublishPlanInput:
        token = (await self.token_provider.access_token()).strip()
        if not token:
            raise ValueError("Control API service access token is empty")
        response = await self.client.get(
            f"/api/v1/publish-plans/{plan_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        plan: dict[str, Any] = response.json()
        snapshot = plan["snapshot"]
        targets: list[PublishTargetInput] = []
        for target in plan["publishTargets"]:
            device_id = target.get("device_id")
            if not device_id:
                raise ValueError(f"publish target {target['id']} has no explicit device assignment")
            targets.append(
                PublishTargetInput(
                    tenant_id=tenant_id,
                    plan_id=plan_id,
                    target_id=target["id"],
                    snapshot_id=snapshot["id"],
                    device_id=device_id,
                    requires_human_confirmation=False,
                )
            )
        return PublishPlanInput(plan_id=plan_id, targets=tuple(targets))


class TemporalPublishSink:
    def __init__(self, client: Client, loader: PlanLoader, task_queue: str) -> None:
        self.client = client
        self.loader = loader
        self.task_queue = task_queue

    async def publish(self, event: EventEnvelope) -> None:
        if not self._starts_workflow(event):
            return
        workflow_id = f"publish-plan/{event.aggregate_id}"
        input = await self.loader.load(event.tenant_id, event.aggregate_id)
        try:
            await self.client.start_workflow(
                PublishPlanWorkflow.run,
                input,
                id=workflow_id,
                task_queue=self.task_queue,
            )
        except WorkflowAlreadyStartedError:
            handle = self.client.get_workflow_handle(workflow_id)
            description = await handle.describe()
            if description.status not in {
                WorkflowExecutionStatus.RUNNING,
                WorkflowExecutionStatus.COMPLETED,
            }:
                raise

    @staticmethod
    def _starts_workflow(event: EventEnvelope) -> bool:
        if event.event_type == "publish.plan.submitted":
            return not bool(event.payload.get("requiresApproval"))
        return (
            event.event_type == "publish.plan.approval_decided"
            and event.payload.get("decision") == "APPROVED"
        )
