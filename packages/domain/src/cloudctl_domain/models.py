"""Immutable value objects crossing application and workflow boundaries."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .events import canonical_hash, new_uuid7
from .rbac import Role
from .states import PublishState


@dataclass(frozen=True, slots=True)
class Actor:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    roles: frozenset[Role]
    mfa: bool
    request_id: str
    ip: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True, slots=True)
class PublishSnapshot:
    tenant_id: uuid.UUID
    plan_id: uuid.UUID
    content_revision_id: uuid.UUID
    automation_package_version_id: uuid.UUID
    payload: dict[str, Any]
    approved_by: uuid.UUID | None = None
    id: uuid.UUID = field(default_factory=new_uuid7)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def payload_sha256(self) -> str:
        return canonical_hash(self.payload)


@dataclass(frozen=True, slots=True)
class Approval:
    plan_id: uuid.UUID
    creator_id: uuid.UUID
    approver_id: uuid.UUID
    decision: str
    id: uuid.UUID = field(default_factory=new_uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.creator_id == self.approver_id:
            raise ValueError("creator and approver must be different users")


@dataclass(frozen=True, slots=True)
class DeviceLease:
    tenant_id: uuid.UUID
    device_id: uuid.UUID
    lease_id: uuid.UUID
    owner_workflow_id: str
    fencing_token: int
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class CommitIntent:
    tenant_id: uuid.UUID
    target_id: uuid.UUID
    fencing_token: int
    before_commit_evidence_id: uuid.UUID
    attempt_no: int = 1
    id: uuid.UUID = field(default_factory=new_uuid7)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.attempt_no != 1:
            raise ValueError("commit intent only supports attempt_no=1")


@dataclass(frozen=True, slots=True)
class PublishTargetResult:
    target_id: uuid.UUID
    state: PublishState
    evidence_ids: tuple[uuid.UUID, ...] = ()
    detail: str | None = None
