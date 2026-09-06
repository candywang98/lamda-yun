"""Stable, serialization-friendly workflow contracts."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PublishTargetInput:
    tenant_id: str
    plan_id: str
    target_id: str
    snapshot_id: str
    device_id: str
    requires_human_confirmation: bool = False


@dataclass(frozen=True)
class Lease:
    device_id: str
    lease_id: str
    owner_workflow_id: str
    fencing_token: int
    expires_at: str


@dataclass(frozen=True)
class CommitIntent:
    id: str
    target_id: str
    fencing_token: int
    before_commit_evidence_id: str


@dataclass(frozen=True)
class ReconcileObservation:
    state: str
    detail: str | None = None
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TargetOutcome:
    target_id: str
    state: str
    detail: str | None = None
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublishPlanInput:
    plan_id: str
    targets: tuple[PublishTargetInput, ...]
    page_size: int = 50


@dataclass(frozen=True)
class PublishPlanOutcome:
    plan_id: str
    targets: tuple[TargetOutcome, ...] = field(default_factory=tuple)
