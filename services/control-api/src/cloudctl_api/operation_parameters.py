"""Strong parameter contracts for the Web-backed safe operation mappings."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .operation_catalog import BY_CATALOG_ID, XY_TASK_CATALOG_IDS

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
    # K05 erratum (2026-09-16): at most 49 selectable xianyu covers (tile 0 is
    # the camera shutter); the MediaDelivery transport cap (50) is separate.
    mediaAssetIds: list[str] = Field(default_factory=list, max_length=49)
    productId: str | None = Field(default=None, min_length=1, max_length=36)


# ---------------------------------------------------------------------------
# A09: strict core parameter contracts for the registered xy-tasks actions.
# Budget/target discipline: every budget-like or target-like field is a
# declared Literal/bounded value, so any drift (unknown package tier, unknown
# selection mode, out-of-bounds cut) fails validation instead of silently
# re-targeting the action. Pending-device-verification actions declare an
# empty contract: nothing may be validated until T102 verifies the surface.
# ---------------------------------------------------------------------------


class XianyuPublishPostParameters(StrictParameters):
    """Pending T102: no parameter may be declared before real-device verification."""


class XianyuPolishGoodsParameters(StrictParameters):
    intervalSeconds: int = Field(default=60, ge=5, le=3600)
    schedule: str | None = Field(default=None, min_length=1, max_length=64)


class XianyuShelfUpParameters(StrictParameters):
    intervalSeconds: int = Field(default=300, ge=5, le=3600)


class XianyuShelfDownParameters(StrictParameters):
    exposure: int | None = Field(default=None, ge=0, le=1_000_000)
    views: int | None = Field(default=None, ge=0, le=1_000_000)
    wants: int | None = Field(default=None, ge=0, le=1_000_000)
    keyword: str | None = Field(default=None, min_length=1, max_length=64)


class XianyuDeleteGoodsParameters(StrictParameters):
    target: Literal["sold_out", "manually_selected", "shelf_down"]


class XianyuDeletePostParameters(StrictParameters):
    """Pending T102: no parameter may be declared before real-device verification."""


class XianyuBindAccountParameters(StrictParameters):
    memberName: str = Field(min_length=1, max_length=64)


class XianyuCoinCheckinParameters(StrictParameters):
    jumpTask: bool = False


class XianyuCoinDiscountParameters(StrictParameters):
    dikouType: Literal["order_fees", "postage"]
    dikouTarget: Literal["all_eligible", "manually_selected"]
    intervalSeconds: int | None = Field(default=None, ge=5, le=3600)


class XianyuCoinPromoteParameters(StrictParameters):
    # Budget/target red line: the promotion item and the coin-budget package
    # are closed Literals — an undeclared tier or target is a drift and is
    # rejected (the feature itself is additionally policy-blocked).
    promoteItem: Literal["manually_selected", "recently_listed"]
    promotePackage: Literal["coins_60", "coins_120", "coins_300", "coins_600"]


class XianyuBargainParameters(StrictParameters):
    xiaodaoType: Literal["gentle", "standard", "aggressive"]
    privateMessage: bool = False


class XianyuPriceCutParameters(StrictParameters):
    # Exactly one cut dimension; both or neither is a contract violation.
    percentCut: int | None = Field(default=None, ge=1, le=50)
    amountCut: str | None = Field(default=None, pattern=r"^[0-9]+(\.[0-9]{1,2})?$", max_length=16)
    target: Literal["all_listings", "manually_selected"]

    @model_validator(mode="after")
    def exactly_one_cut(self) -> XianyuPriceCutParameters:
        if (self.percentCut is None) == (self.amountCut is None):
            raise ValueError("exactly one of percentCut or amountCut is required")
        return self


class XianyuReviewParameters(StrictParameters):
    reviewBody: str = Field(min_length=1, max_length=500)
    reviewTarget: Literal["recent_buyers", "all_unreviewed"]


class XianyuRestartAppParameters(StrictParameters):
    """No tunables; failures surface a reasonCode per the field-map constraint."""


class XianyuDeleteFeedParameters(StrictParameters):
    quantity: int = Field(ge=1, le=100)


class XianyuDeleteMessageParameters(StrictParameters):
    messageAction: Literal["clear_all", "older_than_7_days"]


class XianyuDeleteCommentParameters(StrictParameters):
    quantity: int = Field(ge=1, le=100)


class XianyuDraftPublishParameters(StrictParameters):
    pass


class XianyuReeditParameters(StrictParameters):
    intervalSeconds: int | None = Field(default=None, ge=5, le=3600)
    addressPool: bool = False


class XianyuWuyoumaiParameters(StrictParameters):
    wuyoumaiType: Literal["standard", "full_hosting"]


class XianyuFastReeditParameters(StrictParameters):
    autoShortTitle: bool = False


class XianyuFastShelfDownParameters(StrictParameters):
    pass


class XianyuCollectListingsParameters(StrictParameters):
    pass


class GenericAddressPoolParameters(StrictParameters):
    """Shared pool contract is owned by the content lanes; nothing declared here."""


class DeviceAddressPoolParameters(StrictParameters):
    """Shared pool contract is owned by the content lanes; nothing declared here."""


class DescriptionPoolParameters(StrictParameters):
    """Shared pool contract is owned by the content lanes; nothing declared here."""


class TagPoolParameters(StrictParameters):
    """Shared pool contract is owned by the content lanes; nothing declared here."""


class XianyuWatermarkParameters(StrictParameters):
    ruleVersionId: str | None = Field(default=None, min_length=1, max_length=128)


class ForbiddenWordsScanParameters(StrictParameters):
    policyVersion: str | None = Field(default=None, min_length=1, max_length=128)


class VideoGuideParameters(StrictParameters):
    """Guide-only inventory registration; no execution parameters."""


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


# A09 page models for the xy-tasks feature forms. Device-action pages collect
# a device scope plus the main-app constraint; shared-service pages reuse the
# existing shared shapes. All are extra="forbid" strict models.


class XianyuPublishPostPageParameters(StrictParameters):
    """Validation-only page contract while xy-tasks-02 awaits T102."""

    contentScope: str = Field(min_length=1, max_length=80)
    accountScope: str = Field(min_length=1, max_length=80)
    distributionMode: str = Field(min_length=1, max_length=80)
    schedule: str = Field(min_length=1, max_length=40)
    dryRun: Literal[True]


class XianyuDeviceTaskPageParameters(StrictParameters):
    deviceScope: Literal["all_authorized", "selected_group", "manually_selected"] = (
        "manually_selected"
    )
    executionApp: Literal["xianyu_main"] = "xianyu_main"
    schedule: str | None = Field(default=None, min_length=1, max_length=40)


class PoolPageParameters(StrictParameters):
    entryKeyword: str = Field(default="", max_length=64)
    activeOnly: bool = False


class VideoGuidePageParameters(StrictParameters):
    topic: str = Field(default="", max_length=80)


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
    # A09 xy-tasks registrations.
    "xianyu.publish_post": XianyuPublishPostParameters,
    "xianyu.polish_goods": XianyuPolishGoodsParameters,
    "xianyu.shelf_up": XianyuShelfUpParameters,
    "xianyu.shelf_down": XianyuShelfDownParameters,
    "xianyu.delete_goods": XianyuDeleteGoodsParameters,
    "xianyu.delete_post": XianyuDeletePostParameters,
    "xianyu.bind_account": XianyuBindAccountParameters,
    "xianyu.checkin_coins": XianyuCoinCheckinParameters,
    "xianyu.coin_discount": XianyuCoinDiscountParameters,
    "xianyu.coin_promote": XianyuCoinPromoteParameters,
    "xianyu.bargain": XianyuBargainParameters,
    "xianyu.price_cut": XianyuPriceCutParameters,
    "xianyu.review": XianyuReviewParameters,
    "xianyu.restart_app": XianyuRestartAppParameters,
    "xianyu.delete_feed": XianyuDeleteFeedParameters,
    "xianyu.delete_message": XianyuDeleteMessageParameters,
    "xianyu.delete_comment": XianyuDeleteCommentParameters,
    "xianyu.draft_publish": XianyuDraftPublishParameters,
    "xianyu.reedit": XianyuReeditParameters,
    "xianyu.wuyoumai": XianyuWuyoumaiParameters,
    "xianyu.fast_reedit": XianyuFastReeditParameters,
    "xianyu.fast_shelf_down": XianyuFastShelfDownParameters,
    "xianyu.collect_listings": XianyuCollectListingsParameters,
    "xianyu.shared.generic_address_pool": GenericAddressPoolParameters,
    "xianyu.shared.device_address_pool": DeviceAddressPoolParameters,
    "xianyu.shared.description_pool": DescriptionPoolParameters,
    "xianyu.shared.tag_pool": TagPoolParameters,
    "xianyu.shared.watermark": XianyuWatermarkParameters,
    "content.forbidden_words.scan": ForbiddenWordsScanParameters,
    "xianyu.guide.videos": VideoGuideParameters,
}

# Device-action xy-tasks features share the device-scope page shape.
_XY_DEVICE_TASK_FEATURES = (
    "xy-tasks-03",
    "xy-tasks-04",
    "xy-tasks-05",
    "xy-tasks-06",
    "xy-tasks-07",
    "xy-tasks-08",
    "xy-tasks-09",
    "xy-tasks-10",
    "xy-tasks-11",
    "xy-tasks-12",
    "xy-tasks-13",
    "xy-tasks-14",
    "xy-tasks-15",
    "xy-tasks-16",
    "xy-tasks-17",
    "xy-tasks-18",
    "xy-tasks-19",
    "xy-tasks-20",
    "xy-tasks-21",
    "xy-tasks-22",
    "xy-tasks-23",
    "xy-tasks-24",
)
_XY_POOL_FEATURES = ("xy-tasks-25", "xy-tasks-26", "xy-tasks-27", "xy-tasks-28")

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
    "xy-tasks-02": XianyuPublishPostPageParameters,
    "zz-tasks-01": PlatformPublishPageParameters,
    "red-tasks-01": PlatformPublishPageParameters,
    "assets-01": WatermarkPageParameters,
    "assets-02": AssetPageParameters,
    **{feature_id: XianyuDeviceTaskPageParameters for feature_id in _XY_DEVICE_TASK_FEATURES},
    **{feature_id: PoolPageParameters for feature_id in _XY_POOL_FEATURES},
    "xy-tasks-29": WatermarkPageParameters,
    "xy-tasks-30": ContentPolicyPageParameters,
    "xy-tasks-31": VideoGuidePageParameters,
}

# A09: xy-tasks feature → registered operation key, derived from the catalog
# registration so the field-map identity chain stays single-sourced.
_XY_PAGE_OPERATION_KEYS = {
    catalog_id: BY_CATALOG_ID[catalog_id].key for catalog_id in XY_TASK_CATALOG_IDS
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
    "zz-tasks-01": "publish_plans.snapshot.validate",
    "red-tasks-01": "publish_plans.snapshot.validate",
    "assets-01": "watermarks.preview.render",
    "assets-02": "media.derivative.generate",
    **_XY_PAGE_OPERATION_KEYS,
}
if set(PAGE_OPERATION_KEYS) != set(PAGE_MODELS):
    raise ValueError("every mapped feature must expose exactly one page parameter model")


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
