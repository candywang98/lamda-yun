"""Contracts for catalog-backed asynchronous operations."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


class OperationModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class OperationTaskCreate(OperationModel):
    operation_key: str = Field(alias="operationKey", min_length=3, max_length=160)
    feature_id: str | None = Field(default=None, alias="featureId", min_length=3, max_length=160)
    resource_id: str = Field(alias="resourceId", min_length=1, max_length=255)
    parameters: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class BatchOperationCreate(OperationModel):
    operation_key: str = Field(alias="operationKey", min_length=3, max_length=160)
    feature_id: str | None = Field(default=None, alias="featureId", min_length=3, max_length=160)
    resource_ids: list[str] = Field(alias="resourceIds", min_length=2, max_length=500)
    parameters: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("resource_ids")
    @classmethod
    def unique_resources(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 255 for value in normalized):
            raise ValueError("resource IDs must contain 1 to 255 characters")
        if len(normalized) != len(set(normalized)):
            raise ValueError("resourceIds must be unique")
        return normalized


class OperationItemResultUpdate(OperationModel):
    status: Literal["SUCCEEDED", "FAILED", "BLOCKED"]
    error_code: str | None = Field(default=None, alias="errorCode", max_length=80)
    detail: str | None = Field(default=None, max_length=2000)
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs", max_length=50)

    @field_validator("evidence_refs")
    @classmethod
    def safe_evidence_refs(cls, values: list[str]) -> list[str]:
        for value in values:
            if len(value) > 512:
                raise ValueError("evidence references must be at most 512 characters")
            parsed = urlsplit(value)
            if parsed.scheme not in {"s3", "https"} or not parsed.netloc:
                raise ValueError("evidence references must use an absolute s3:// or https:// URL")
            if parsed.username is not None or parsed.password is not None:
                raise ValueError("evidence references cannot contain URL credentials")
        return values

    @model_validator(mode="after")
    def terminal_result_is_consistent(self) -> OperationItemResultUpdate:
        if self.status == "SUCCEEDED" and self.error_code is not None:
            raise ValueError("successful operation results cannot include errorCode")
        if self.status in {"FAILED", "BLOCKED"} and self.error_code is None:
            raise ValueError("failed or blocked operation results require errorCode")
        return self


class OperationCancelRequest(OperationModel):
    reason: str = Field(min_length=1, max_length=1000)


class OperationApprovalRequest(OperationModel):
    reason: str = Field(min_length=2, max_length=1000)


class OperationCatalogView(OperationModel):
    key: str
    module: str
    resource_type: str
    batch_allowed: bool
    required_permission: str
    authorized: bool
    allowed: bool
    executor_available: bool
    execution_state: Literal["implemented", "contract_only"]
    allowed_parameters: list[str]
    parameter_schema: dict[str, Any]
    description: str
    risk: Literal["standard", "approval"]
    feature_ids: list[str]


class OperationFeatureView(OperationModel):
    feature_id: str
    index: int
    module: str
    module_label: str
    stage: str
    title: str
    mode: Literal["guide", "table", "form", "assets", "insight", "settings"]
    operation_key: str | None
    policy: Literal["mapped", "unmapped", "blocked"]
    execution_state: Literal["implemented", "contract_only", "ui_only", "blocked"]
    risk: Literal["standard", "approval", "blocked"]
    authorized: bool
    allowed: bool
    executable: bool
    reason: str


MAX_FEATURE_CONFIG_BYTES = 65_536
MAX_FEATURE_CONFIG_DEPTH = 8
MAX_FEATURE_CONFIG_NODES = 2_048
MAX_FEATURE_CONFIG_ITEMS = 256
MAX_FEATURE_CONFIG_KEY_LENGTH = 128
MAX_FEATURE_CONFIG_STRING_LENGTH = 8_192
DANGEROUS_FEATURE_CONFIG_KEYS = frozenset(
    {
        "allowed",
        "captcha",
        "command",
        "constructor",
        "executable",
        "executionstate",
        "frida",
        "mitm",
        "operationkey",
        "policy",
        "proto",
        "prototype",
        "proxy",
        "risk",
        "script",
        "shell",
        "where",
    }
)
DANGEROUS_FEATURE_CONFIG_PREFIXES = (
    "adb",
    "captcha",
    "command",
    "frida",
    "mitm",
    "proxy",
    "script",
    "shell",
)
DANGEROUS_FEATURE_CONFIG_SUFFIXES = (
    "credential",
    "password",
    "pem",
    "privatekey",
    "secret",
    "token",
)


def validate_feature_configuration(value: dict[str, Any]) -> dict[str, Any]:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("configuration must contain finite JSON values") from exc
    if len(encoded) > MAX_FEATURE_CONFIG_BYTES:
        raise ValueError("configuration exceeds 64 KiB")

    node_count = 0

    def inspect(current: Any, depth: int) -> None:
        nonlocal node_count
        node_count += 1
        if node_count > MAX_FEATURE_CONFIG_NODES:
            raise ValueError("configuration exceeds the node limit")
        if depth > MAX_FEATURE_CONFIG_DEPTH:
            raise ValueError("configuration exceeds the maximum nesting depth")
        if isinstance(current, dict):
            if len(current) > MAX_FEATURE_CONFIG_ITEMS:
                raise ValueError("configuration object exceeds the item limit")
            for key, child in current.items():
                if not isinstance(key, str) or not key or len(key) > MAX_FEATURE_CONFIG_KEY_LENGTH:
                    raise ValueError("configuration keys must contain 1 to 128 characters")
                if any(ord(character) < 32 for character in key):
                    raise ValueError("configuration keys cannot contain control characters")
                normalized = re.sub(r"[^a-z0-9]+", "", key.casefold())
                if (
                    normalized in DANGEROUS_FEATURE_CONFIG_KEYS
                    or normalized.startswith(DANGEROUS_FEATURE_CONFIG_PREFIXES)
                    or normalized.endswith(DANGEROUS_FEATURE_CONFIG_SUFFIXES)
                ):
                    raise ValueError(f"dangerous configuration key is prohibited: {key}")
                inspect(child, depth + 1)
        elif isinstance(current, list):
            if len(current) > MAX_FEATURE_CONFIG_ITEMS:
                raise ValueError("configuration array exceeds the item limit")
            for child in current:
                inspect(child, depth + 1)
        elif isinstance(current, str):
            if len(current) > MAX_FEATURE_CONFIG_STRING_LENGTH:
                raise ValueError("configuration string exceeds 8192 characters")
        elif isinstance(current, float) and not math.isfinite(current):
            raise ValueError("configuration must contain finite JSON values")
        elif current is not None and not isinstance(current, bool | int | float):
            raise ValueError("configuration must contain JSON values only")

    inspect(value, 1)
    return value


class OperationFeatureConfigDraftPut(OperationModel):
    configuration: dict[str, Any] = Field(
        description=(
            "Tenant-scoped, non-executable draft JSON; limited to 64 KiB, eight nesting "
            "levels, and safe keys."
        )
    )
    expected_version: int = Field(alias="expectedVersion", ge=0)

    @field_validator("configuration")
    @classmethod
    def safe_configuration(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_feature_configuration(value)


class OperationFeatureConfigDraftView(OperationModel):
    feature_id: str
    configuration: dict[str, Any]
    version: int
    exists: bool
    created_at: datetime | None
    updated_at: datetime | None
    updated_by: str | None


OperationTaskStatus = Literal[
    "PENDING_APPROVAL",
    "REJECTED",
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "PARTIAL",
    "FAILED",
    "CANCELED",
]
OperationItemStatus = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "BLOCKED", "CANCELED"]


class OperationTaskItemView(OperationModel):
    id: str
    resource_id: str
    status: OperationItemStatus
    error_code: str | None
    detail: str | None
    evidence_refs: list[str]
    updated_at: datetime


class OperationTaskSummaryView(OperationModel):
    id: str
    tenant_id: str
    operation_key: str
    feature_id: str | None
    module: str
    request_sha256: str
    requested_by: str
    status: OperationTaskStatus
    parameters: dict[str, Any]
    context: dict[str, Any]
    risk: Literal["standard", "approval"]
    execution_state: Literal["implemented", "contract_only"]
    executor_available: bool
    total_count: int
    succeeded_count: int
    failed_count: int
    blocked_count: int
    canceled_count: int
    cancel_requested: bool
    result_summary: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    approval_decision: Literal["APPROVED", "REJECTED"] | None
    approval_reason: str | None
    approved_by: str | None
    decided_at: datetime | None


class OperationTaskView(OperationTaskSummaryView):
    items: list[OperationTaskItemView]


class OperationAuditEventView(OperationModel):
    id: str
    actor_type: Literal["user", "service"]
    actor_id: str
    action: str
    resource_type: str
    resource_id: str
    request_id: str
    workflow_id: str | None
    device_id: str | None
    edge_id: str | None
    result: str
    before_hash: str | None
    after_hash: str | None
    metadata: dict[str, Any]
    occurred_at: datetime


class OperationAuditResultView(OperationModel):
    task: OperationTaskView
    audit_events: list[OperationAuditEventView]
