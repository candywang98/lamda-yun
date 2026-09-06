"""Activity I/O ports and safe development implementations."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from .contracts import CommitIntent, Lease, PublishTargetInput, ReconcileObservation


class ActivityBackend(Protocol):
    async def validate_snapshot(self, input: PublishTargetInput) -> None: ...

    async def acquire_lease(self, input: PublishTargetInput, workflow_id: str) -> Lease: ...

    async def preflight(self, input: PublishTargetInput, lease: Lease) -> None: ...

    async def stage_media(self, input: PublishTargetInput, lease: Lease) -> None: ...

    async def prepare(self, input: PublishTargetInput, lease: Lease) -> str: ...

    async def write_commit_intent(
        self, input: PublishTargetInput, lease: Lease, evidence_id: str
    ) -> CommitIntent: ...

    async def commit_once(
        self, input: PublishTargetInput, lease: Lease, intent: CommitIntent
    ) -> None: ...

    async def reconcile(self, input: PublishTargetInput, lease: Lease) -> ReconcileObservation: ...

    async def mark_state(
        self, input: PublishTargetInput, state: str, detail: str | None
    ) -> None: ...

    async def cleanup(self, input: PublishTargetInput, lease: Lease | None) -> None: ...

    async def release_lease(self, input: PublishTargetInput, lease: Lease) -> None: ...


class ControlPlaneBackend:
    """HTTP persistence adapter. Edge operations stay behind an injected executor."""

    def __init__(
        self,
        base_url: str,
        service_headers: dict[str, str],
        edge: EdgeExecutor,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30)
        self._headers = service_headers
        self._edge = edge

    async def validate_snapshot(self, input: PublishTargetInput) -> None:
        response = await self._client.get(
            f"/api/v1/publish-plans/{input.plan_id}", headers=self._headers
        )
        response.raise_for_status()
        payload = response.json()
        snapshot = payload.get("snapshot")
        if snapshot is None or snapshot.get("id") != input.snapshot_id:
            raise ValueError("workflow input does not match the immutable publish snapshot")

    async def acquire_lease(self, input: PublishTargetInput, workflow_id: str) -> Lease:
        response = await self._client.post(
            f"/api/v1/devices/{input.device_id}/leases",
            headers=self._headers,
            json={"ownerWorkflowId": workflow_id, "ttlSeconds": 60},
        )
        response.raise_for_status()
        value = response.json()
        return Lease(
            device_id=value["device_id"],
            lease_id=value["lease_id"],
            owner_workflow_id=value["owner_workflow_id"],
            fencing_token=value["fencing_token"],
            expires_at=value["expires_at"],
        )

    async def preflight(self, input: PublishTargetInput, lease: Lease) -> None:
        await self._edge.preflight(input, lease)

    async def stage_media(self, input: PublishTargetInput, lease: Lease) -> None:
        await self._edge.stage_media(input, lease)

    async def prepare(self, input: PublishTargetInput, lease: Lease) -> str:
        return await self._edge.prepare(input, lease)

    async def write_commit_intent(
        self, input: PublishTargetInput, lease: Lease, evidence_id: str
    ) -> CommitIntent:
        response = await self._client.post(
            f"/api/v1/publish-targets/{input.target_id}/commit-intents",
            headers=self._headers,
            json={
                "fencingToken": lease.fencing_token,
                "beforeCommitEvidenceId": evidence_id,
            },
        )
        response.raise_for_status()
        value = response.json()
        return CommitIntent(
            id=value["id"],
            target_id=value["target_id"],
            fencing_token=value["fencing_token"],
            before_commit_evidence_id=value["before_commit_evidence_id"],
        )

    async def commit_once(
        self, input: PublishTargetInput, lease: Lease, intent: CommitIntent
    ) -> None:
        await self._edge.commit_once(input, lease, intent)

    async def reconcile(self, input: PublishTargetInput, lease: Lease) -> ReconcileObservation:
        return await self._edge.reconcile(input, lease)

    async def mark_state(self, input: PublishTargetInput, state: str, detail: str | None) -> None:
        response = await self._client.post(
            f"/api/v1/publish-targets/{input.target_id}:state",
            headers=self._headers,
            json={"state": state, "detail": detail},
        )
        response.raise_for_status()

    async def cleanup(self, input: PublishTargetInput, lease: Lease | None) -> None:
        await self._edge.cleanup(input, lease)

    async def release_lease(self, input: PublishTargetInput, lease: Lease) -> None:
        response = await self._client.delete(
            f"/api/v1/devices/{input.device_id}/leases/{lease.lease_id}",
            headers=self._headers,
        )
        response.raise_for_status()


class EdgeExecutor(Protocol):
    async def preflight(self, input: PublishTargetInput, lease: Lease) -> None: ...

    async def stage_media(self, input: PublishTargetInput, lease: Lease) -> None: ...

    async def prepare(self, input: PublishTargetInput, lease: Lease) -> str: ...

    async def commit_once(
        self, input: PublishTargetInput, lease: Lease, intent: CommitIntent
    ) -> None: ...

    async def reconcile(self, input: PublishTargetInput, lease: Lease) -> ReconcileObservation: ...

    async def cleanup(self, input: PublishTargetInput, lease: Lease | None) -> None: ...


@dataclass
class InMemoryActivityBackend:
    """Stateful test/development backend that enforces single-shot commit."""

    reconciliation: ReconcileObservation = field(
        default_factory=lambda: ReconcileObservation(state="SUCCEEDED")
    )
    states: list[str] = field(default_factory=list)
    commit_calls: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    released: set[str] = field(default_factory=set)

    async def validate_snapshot(self, input: PublishTargetInput) -> None:
        if not input.snapshot_id or not input.target_id or not input.device_id:
            raise ValueError("publish target input is incomplete")

    async def acquire_lease(self, input: PublishTargetInput, workflow_id: str) -> Lease:
        return Lease(
            device_id=input.device_id,
            lease_id=str(uuid.uuid4()),
            owner_workflow_id=workflow_id,
            fencing_token=1,
            expires_at="2099-01-01T00:00:00Z",
        )

    async def preflight(self, input: PublishTargetInput, lease: Lease) -> None:
        self._check_lease(input, lease)

    async def stage_media(self, input: PublishTargetInput, lease: Lease) -> None:
        self._check_lease(input, lease)

    async def prepare(self, input: PublishTargetInput, lease: Lease) -> str:
        self._check_lease(input, lease)
        return str(uuid.uuid4())

    async def write_commit_intent(
        self, input: PublishTargetInput, lease: Lease, evidence_id: str
    ) -> CommitIntent:
        self._check_lease(input, lease)
        return CommitIntent(
            id=str(uuid.uuid4()),
            target_id=input.target_id,
            fencing_token=lease.fencing_token,
            before_commit_evidence_id=evidence_id,
        )

    async def commit_once(
        self, input: PublishTargetInput, lease: Lease, intent: CommitIntent
    ) -> None:
        self._check_lease(input, lease)
        if intent.fencing_token != lease.fencing_token:
            raise ValueError("commit intent fencing token mismatch")
        self.commit_calls[input.target_id] += 1
        if self.commit_calls[input.target_id] > 1:
            raise RuntimeError("commit_once called more than once")

    async def reconcile(self, input: PublishTargetInput, lease: Lease) -> ReconcileObservation:
        self._check_lease(input, lease)
        return self.reconciliation

    async def mark_state(self, input: PublishTargetInput, state: str, detail: str | None) -> None:
        self.states.append(state)

    async def cleanup(self, input: PublishTargetInput, lease: Lease | None) -> None:
        return None

    async def release_lease(self, input: PublishTargetInput, lease: Lease) -> None:
        self.released.add(lease.lease_id)

    @staticmethod
    def _check_lease(input: PublishTargetInput, lease: Lease) -> None:
        if lease.device_id != input.device_id or lease.fencing_token < 1:
            raise ValueError("invalid fencing lease")
