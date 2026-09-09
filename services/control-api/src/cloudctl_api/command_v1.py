"""CommandV1 frozen instruction contract for Companion Recipe execution."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROTOCOL_VERSION = "cloudctl.command/v1"
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
PACKAGE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
FORBIDDEN_KEYS = frozenset(
    {
        "shell",
        "dex",
        "js",
        "javascript",
        "frida",
        "argv",
        "payload",
        "script",
        "bytecode",
    }
)
COMMAND_PACKAGES = {
    "xianyu.publish_listing.v1": "com.taobao.idlefish",
    "xianyu.collect_orders.v1": "com.taobao.idlefish",
    "xiaohongshu.publish_note.v1": "com.xingin.xhs",
    "device.probe_capabilities.v1": None,
}
REQUIRED_CAPABILITIES: dict[str, list[str]] = {
    "xianyu.publish_listing.v1": ["accessibility", "network"],
    "xianyu.collect_orders.v1": ["accessibility", "network"],
    "xiaohongshu.publish_note.v1": ["accessibility", "network"],
    "device.probe_capabilities.v1": ["accessibility", "network"],
}
CommandType = Literal[
    "xianyu.publish_listing.v1",
    "xianyu.collect_orders.v1",
    "xiaohongshu.publish_note.v1",
    "device.probe_capabilities.v1",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)


class SnapshotRef(StrictModel):
    id: str
    sha256: str

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        if not ID_PATTERN.fullmatch(value):
            raise ValueError("id is invalid")
        return value

    @field_validator("sha256")
    @classmethod
    def valid_sha(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 is invalid")
        return value


class RecipeRef(StrictModel):
    version_id: str = Field(alias="versionId")
    sha256: str
    engine_min_version: int = Field(alias="engineMinVersion", ge=1, le=1000)

    @field_validator("version_id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        if not ID_PATTERN.fullmatch(value):
            raise ValueError("versionId is invalid")
        return value

    @field_validator("sha256")
    @classmethod
    def valid_sha(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 is invalid")
        return value


class LeaseRef(StrictModel):
    control_epoch: int = Field(alias="controlEpoch", ge=1)
    expires_at: str = Field(alias="expiresAt", min_length=10, max_length=40)


class XianyuPublishListingParams(StrictModel):
    listing_body: str = Field(alias="listingBody", min_length=1, max_length=1024)
    price: str
    media_asset_ids: list[str] = Field(default_factory=list, alias="mediaAssetIds", max_length=50)
    product_id: str | None = Field(default=None, alias="productId", min_length=1, max_length=36)

    @field_validator("price")
    @classmethod
    def valid_price(cls, value: str) -> str:
        if not re.fullmatch(r"^[0-9]+(\.[0-9]{1,2})?$", value):
            raise ValueError("price is invalid")
        return value


class XianyuCollectOrdersParams(StrictModel):
    role: Literal["ALL_VISIBLE", "BUYER", "SELLER"]
    limit: int | None = Field(default=None, ge=1, le=5000)


class XiaohongshuPublishNoteParams(StrictModel):
    title: str = Field(min_length=1, max_length=64)
    body: str = Field(min_length=1, max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    media_asset_ids: list[str] = Field(default_factory=list, alias="mediaAssetIds", max_length=18)


class EmptyParams(StrictModel):
    pass


class CommandV1(StrictModel):
    protocol_version: Literal["cloudctl.command/v1"] = Field(alias="protocolVersion")
    task_id: str = Field(alias="taskId")
    attempt_id: str = Field(alias="attemptId")
    command_type: CommandType = Field(alias="commandType")
    device_id: str = Field(alias="deviceId")
    account_id: str = Field(alias="accountId")
    binding_version: int = Field(alias="bindingVersion", ge=1)
    snapshot: SnapshotRef
    recipe: RecipeRef
    target_package: str = Field(alias="targetPackage")
    required_capabilities: list[
        Literal["accessibility", "mediaProjection", "network", "foregroundService"]
    ] = Field(alias="requiredCapabilities", max_length=32)
    lease: LeaseRef
    media_delivery_id: str | None = Field(default=None, alias="mediaDeliveryId")
    legacy_steps_enabled: bool = Field(default=False, alias="legacyStepsEnabled")
    parameters: dict[str, Any]

    @field_validator("task_id", "attempt_id", "device_id", "account_id")
    @classmethod
    def valid_ids(cls, value: str) -> str:
        if not ID_PATTERN.fullmatch(value):
            raise ValueError("identity field is invalid")
        return value

    @field_validator("target_package")
    @classmethod
    def valid_package(cls, value: str) -> str:
        if not PACKAGE_PATTERN.fullmatch(value):
            raise ValueError("targetPackage is invalid")
        return value

    @field_validator("required_capabilities")
    @classmethod
    def unique_capabilities(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("requiredCapabilities must be unique")
        return value

    @model_validator(mode="after")
    def typed_parameters_and_package(self) -> CommandV1:
        expected_package = COMMAND_PACKAGES[self.command_type]
        if expected_package and self.target_package != expected_package:
            raise ValueError("targetPackage does not match commandType")
        parsers = {
            "xianyu.publish_listing.v1": XianyuPublishListingParams,
            "xianyu.collect_orders.v1": XianyuCollectOrdersParams,
            "xiaohongshu.publish_note.v1": XiaohongshuPublishNoteParams,
            "device.probe_capabilities.v1": EmptyParams,
        }
        parsers[self.command_type].model_validate(self.parameters)
        return self


def _reject_forbidden_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = key.lower()
            if any(fragment in lowered for fragment in FORBIDDEN_KEYS):
                raise ValueError("command contains unauthorized execution fields")
            _reject_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_keys(item)


def parse_command_v1(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_forbidden_keys(payload)
    command = CommandV1.model_validate(payload)
    return command.model_dump(mode="json", by_alias=True)


def _lease_expires_iso(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.strftime("%Y-%m-%dT%H:%M:%SZ")


def _typed_parameters(command_type: str, parameters: dict[str, Any] | None) -> dict[str, Any]:
    parsers = {
        "xianyu.publish_listing.v1": XianyuPublishListingParams,
        "xianyu.collect_orders.v1": XianyuCollectOrdersParams,
        "xiaohongshu.publish_note.v1": XiaohongshuPublishNoteParams,
        "device.probe_capabilities.v1": EmptyParams,
    }
    parsed = parsers[command_type].model_validate(parameters or {})
    dumped = parsed.model_dump(mode="json", by_alias=True, exclude_none=True)
    if command_type == "xianyu.collect_orders.v1" and "limit" not in dumped:
        dumped["limit"] = None
    return dumped


def command_v1_from_task(
    *,
    task_id: str,
    attempt_id: str,
    command_type: str,
    device_id: str,
    account_id: str,
    binding_version: int,
    target_package: str,
    command_payload: dict[str, Any] | None,
    control_epoch: int,
    lease_expires_at: datetime,
    media_delivery_id: str | None = None,
    legacy_steps_enabled: bool = False,
    published_recipe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from .builtin_recipes import builtin_recipe_ref

    payload = dict(command_payload or {})
    snapshot_sha = payload.get("snapshotSha256")
    if not isinstance(snapshot_sha, str) or not SHA256_PATTERN.fullmatch(snapshot_sha):
        raise ValueError("snapshotSha256 is required to mint CommandV1")
    snapshot_id = payload.get("snapshotId")
    if not isinstance(snapshot_id, str) or not snapshot_id:
        snapshot_id = f"snap-{task_id}"
    recipe = published_recipe if isinstance(published_recipe, dict) else payload.get("recipe")
    if not isinstance(recipe, dict):
        recipe = builtin_recipe_ref(command_type)
    delivery = media_delivery_id or payload.get("mediaDeliveryId")
    command: dict[str, Any] = {
        "protocolVersion": PROTOCOL_VERSION,
        "taskId": task_id,
        "attemptId": attempt_id,
        "commandType": command_type,
        "deviceId": device_id,
        "accountId": account_id,
        "bindingVersion": binding_version,
        "snapshot": {"id": snapshot_id, "sha256": snapshot_sha},
        "recipe": recipe,
        "targetPackage": target_package,
        "requiredCapabilities": list(REQUIRED_CAPABILITIES[command_type]),
        "lease": {
            "controlEpoch": control_epoch,
            "expiresAt": _lease_expires_iso(lease_expires_at),
        },
        "legacyStepsEnabled": legacy_steps_enabled,
        "parameters": _typed_parameters(command_type, payload.get("parameters") or {}),
    }
    if isinstance(delivery, str) and delivery:
        command["mediaDeliveryId"] = delivery
    return parse_command_v1(command)
