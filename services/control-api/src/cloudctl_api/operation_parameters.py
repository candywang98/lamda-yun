"""Strong parameter contracts for the Web-backed safe operation mappings."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

AccountCheck = Literal["authorization", "binding", "expiry"]


def default_account_checks() -> list[AccountCheck]:
    return ["authorization", "binding", "expiry"]


class StrictParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AccountHealthParameters(StrictParameters):
    checks: list[AccountCheck] = Field(
        default_factory=default_account_checks,
        min_length=1,
        max_length=3,
    )


class DeviceCapabilityParameters(StrictParameters):
    includeApps: bool = False


class EvidenceExportParameters(StrictParameters):
    format: Literal["json", "csv"] = "json"
    redact: bool = True


class WatermarkPreviewParameters(StrictParameters):
    ruleVersionId: str | None = Field(default=None, min_length=1, max_length=128)


class GroupReindexParameters(StrictParameters):
    dryRun: bool = True


class PublishSnapshotParameters(StrictParameters):
    strict: bool = True


class WorkRevisionParameters(StrictParameters):
    policyVersion: str | None = Field(default=None, min_length=1, max_length=128)


class MediaDerivativeParameters(StrictParameters):
    derivativeProfileId: str | None = Field(default=None, min_length=1, max_length=128)


class DevicePageParameters(StrictParameters):
    healthScope: str = Field(min_length=1, max_length=80)
    clientVersion: str = Field(min_length=1, max_length=80)
    groupNumber: str = Field(min_length=1, max_length=80)
    includeOffline: bool


class AccountPageParameters(StrictParameters):
    licenseKey: Literal[""]
    licenseAction: Literal["激活", "续费", "升级"]
    deviceQuota: str = Field(min_length=1, max_length=40)
    confirmOwner: bool


class TaskQueuePageParameters(StrictParameters):
    taskKeyword: str = Field(max_length=255)
    runState: str = Field(min_length=1, max_length=80)
    executionApp: str = Field(min_length=1, max_length=80)
    scheduledAfter: str = Field(min_length=1, max_length=40)


class WatermarkPageParameters(StrictParameters):
    watermarkTemplate: str = Field(min_length=1, max_length=80)
    watermarkPosition: Literal["右下角", "左下角", "居中"]
    watermarkOpacity: int = Field(ge=0, le=100)
    previewOnly: Literal[True]


class GroupPageParameters(StrictParameters):
    groupName: str = Field(min_length=1, max_length=160)
    groupCode: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    sortOrder: int = Field(ge=0, le=100_000)
    defaultGroup: bool


class ContentPublishPageParameters(StrictParameters):
    contentScope: str = Field(min_length=1, max_length=80)
    accountScope: str = Field(min_length=1, max_length=80)
    distributionMode: str = Field(min_length=1, max_length=80)
    publishAt: str = Field(min_length=1, max_length=40)


class PlatformPublishPageParameters(StrictParameters):
    contentScope: str = Field(min_length=1, max_length=80)
    accountScope: str = Field(min_length=1, max_length=80)
    distributionMode: str = Field(min_length=1, max_length=80)
    schedule: str = Field(min_length=1, max_length=40)
    dryRun: Literal[True]


class XianyuListingPublishParameters(StrictParameters):
    listingBody: str | None = Field(default=None, min_length=1, max_length=1024)
    price: str | None = Field(default=None, min_length=1, max_length=32)


class XianyuListingPublishPageParameters(StrictParameters):
    listingBody: str = Field(min_length=1, max_length=1024)
    listingPrice: str = Field(min_length=1, max_length=32, pattern=r"^[0-9]+(\.[0-9]{1,2})?$")
    contentScope: str = Field(min_length=1, max_length=80)
    accountScope: str = Field(min_length=1, max_length=80)
    distributionMode: str = Field(min_length=1, max_length=80)
    schedule: str = Field(min_length=1, max_length=40)
    dryRun: bool = False


class ContentPolicyPageParameters(StrictParameters):
    contentScope: str = Field(min_length=1, max_length=80)
    ruleSet: str = Field(min_length=1, max_length=80)
    includeMediaOcr: bool
    onMatch: Literal["仅标记", "转入待复核", "阻止提交"]


class AssetPageParameters(StrictParameters):
    assetName: str = Field(max_length=160)
    assetScope: str = Field(min_length=1, max_length=80)
    fileReference: str = Field(max_length=512)
    versionNote: str = Field(min_length=1, max_length=500)
    active: bool


CORE_MODELS: dict[str, type[StrictParameters]] = {
    "accounts.authorization.health_check": AccountHealthParameters,
    "devices.capabilities.refresh": DeviceCapabilityParameters,
    "task_runs.evidence.export": EvidenceExportParameters,
    "watermarks.preview.render": WatermarkPreviewParameters,
    "groups.membership.reindex": GroupReindexParameters,
    "publish_plans.snapshot.validate": PublishSnapshotParameters,
    "xianyu.listing.publish": XianyuListingPublishParameters,
    "works.revision.validate": WorkRevisionParameters,
    "media.derivative.generate": MediaDerivativeParameters,
}

PAGE_MODELS: dict[str, type[StrictParameters]] = {
    "system-home-02": DevicePageParameters,
    "system-home-03": AccountPageParameters,
    "task-queue-01": TaskQueuePageParameters,
    "product-editor-03": WatermarkPageParameters,
    "product-management-03": GroupPageParameters,
    "product-management-05": ContentPublishPageParameters,
    "product-management-09": ContentPolicyPageParameters,
    "post-management-05": WatermarkPageParameters,
    "post-management-07": ContentPublishPageParameters,
    "post-management-08": ContentPublishPageParameters,
    "xy-tasks-01": XianyuListingPublishPageParameters,
    "xy-tasks-02": PlatformPublishPageParameters,
    "zz-tasks-01": PlatformPublishPageParameters,
    "red-tasks-01": PlatformPublishPageParameters,
    "assets-01": WatermarkPageParameters,
    "assets-02": AssetPageParameters,
}

PAGE_OPERATION_KEYS = {
    "system-home-02": "devices.capabilities.refresh",
    "system-home-03": "accounts.authorization.health_check",
    "task-queue-01": "task_runs.evidence.export",
    "product-editor-03": "watermarks.preview.render",
    "product-management-03": "groups.membership.reindex",
    "product-management-05": "publish_plans.snapshot.validate",
    "product-management-09": "works.revision.validate",
    "post-management-05": "watermarks.preview.render",
    "post-management-07": "publish_plans.snapshot.validate",
    "post-management-08": "publish_plans.snapshot.validate",
    "xy-tasks-01": "xianyu.listing.publish",
    "xy-tasks-02": "publish_plans.snapshot.validate",
    "zz-tasks-01": "publish_plans.snapshot.validate",
    "red-tasks-01": "publish_plans.snapshot.validate",
    "assets-01": "watermarks.preview.render",
    "assets-02": "media.derivative.generate",
}


def validate_operation_parameters(
    operation_key: str,
    feature_id: str | None,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    model = CORE_MODELS.get(operation_key)
    if model is None:
        return parameters
    core = {key: value for key, value in parameters.items() if key != "pageParameters"}
    normalized = model.model_validate(core).model_dump(mode="json", exclude_none=True)
    if "pageParameters" in parameters:
        page_model = PAGE_MODELS.get(feature_id or "")
        if page_model is None:
            raise ValueError("pageParameters require a mapped featureId")
        page = parameters["pageParameters"]
        if not isinstance(page, dict):
            raise ValueError("pageParameters must be an object")
        normalized["pageParameters"] = page_model.model_validate(page).model_dump(mode="json")
    return normalized


def parameter_validation_detail(error: ValidationError) -> str:
    first = error.errors(include_url=False)[0]
    location = ".".join(str(part) for part in first["loc"])
    return f"invalid operation parameter {location}: {first['msg']}"


def operation_parameter_schema(operation_key: str) -> dict[str, Any]:
    model = CORE_MODELS.get(operation_key)
    if model is None:
        return {"type": "object", "additionalProperties": False, "properties": {}}
    return {
        "core": model.model_json_schema(),
        "pageParametersByFeatureId": {
            feature_id: PAGE_MODELS[feature_id].model_json_schema()
            for feature_id, mapped_key in PAGE_OPERATION_KEYS.items()
            if mapped_key == operation_key
        },
    }
