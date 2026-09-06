"""HTTP contracts for short-lived, capability-bounded debug sessions."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

DebugCapability = Literal[
    "view.frame",
    "view.layout",
    "input.tap",
    "input.swipe",
    "input.text",
    "debug.steps",
    "debug.variables",
    "evidence.capture",
]
DebugEvidenceKind = Literal["SCREENSHOT", "UI_TREE", "STEP", "RESULT", "DIAGNOSTIC"]


class DebugModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class DebugSessionCreate(DebugModel):
    device_id: str = Field(alias="deviceId", min_length=1, max_length=36)
    capabilities: list[str] = Field(min_length=1, max_length=16)
    ttl_seconds: int = Field(default=900, alias="ttlSeconds", ge=60, le=900)
    purpose: str = Field(min_length=2, max_length=1000)
    return_url: str | None = Field(default=None, alias="returnUrl", max_length=1024)

    @field_validator("capabilities")
    @classmethod
    def unique_capabilities(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("capabilities cannot contain empty values")
        if len(normalized) != len(set(normalized)):
            raise ValueError("capabilities must be unique")
        return normalized


class DebugSessionExchange(DebugModel):
    launch_code: str = Field(alias="launchCode", min_length=20, max_length=256)


class DebugHeartbeat(DebugModel):
    stage: str = Field(min_length=1, max_length=80)
    event: str = Field(min_length=1, max_length=160)
    detail: str | None = Field(default=None, max_length=2000)
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs", max_length=50)

    @field_validator("evidence_refs")
    @classmethod
    def safe_references(cls, values: list[str]) -> list[str]:
        for value in values:
            if len(value) > 1024:
                raise ValueError("evidence references must be at most 1024 characters")
            parsed = urlsplit(value)
            if parsed.scheme not in {"s3", "https"} or not parsed.netloc:
                raise ValueError("evidence references must use an absolute s3:// or https:// URL")
            if parsed.username is not None or parsed.password is not None:
                raise ValueError("evidence references cannot contain URL credentials")
        return values


class DebugSessionRevoke(DebugModel):
    reason: str = Field(min_length=2, max_length=1000)


class DebugEvidenceCreate(DebugModel):
    kind: DebugEvidenceKind
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    object_ref: str = Field(alias="objectRef", min_length=6, max_length=1024)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DebugSessionView(DebugModel):
    id: str
    tenant_id: str
    edge_id: str
    device_id: str
    lease_id: str | None
    fencing_token: int | None
    created_by: str
    purpose: str
    capabilities: list[DebugCapability]
    status: Literal["PENDING_EXCHANGE", "ACTIVE", "EXPIRED", "REVOKED"]
    expires_at: datetime
    exchanged_at: datetime | None
    last_heartbeat_at: datetime | None
    stage: str | None
    event: str | None
    detail: str | None
    return_url: str | None
    revoked_at: datetime | None
    revoked_by: str | None
    revoke_reason: str | None
    created_at: datetime


class DebugEvidenceView(DebugModel):
    id: str
    session_id: str
    kind: DebugEvidenceKind
    sha256: str
    object_ref: str
    metadata: dict[str, Any]
    created_at: datetime


class DebugSessionDetailView(DebugSessionView):
    evidence: list[DebugEvidenceView]


class DebugSessionCreateResult(DebugModel):
    session: DebugSessionView
    launch_code: str


class DebugSessionExchangeResult(DebugModel):
    session: DebugSessionView
    relay_token: str
    relay_url: str
