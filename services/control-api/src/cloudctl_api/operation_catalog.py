"""Whitelisted asynchronous operations exposed across product modules."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from cloudctl_domain import Permission

# A09 (task-schedule/v1 §2 identity chain): every xy-tasks action in
# docs/phase1/field-map.json is registered as a catalog OperationDefinition.
# The registration records the *catalog identity* (operationId → key), the
# per-action result schema, and whether a production execution lane exists.
# Registration never implies an executor: contract_only / pending entries stay
# fail-closed in both the operations lane (OperationExecutorRegistry) and the
# CommandV1 mint lane (command_factory.PRODUCTION_ALIASES).
OperationAvailability = Literal["executable", "contract_only", "pending_device_verification"]


@dataclass(frozen=True, slots=True)
class OperationDefinition:
    key: str
    module: str
    resource_type: str
    permission: Permission
    batch_allowed: bool
    allowed_parameters: frozenset[str]
    description: str
    risk: Literal["standard", "approval"] = "standard"
    # Terminal result schema identity for this action. Distinct per action
    # family: a polish must report a polish result, a deletion a deleted
    # result, a price change a price_updated result. Never a generic
    # "success"/"deleted" blob shared across unrelated actions.
    result_type: str = ""
    # field-map.json catalog identity (xy-tasks-01..31) when this definition
    # registers one of the 31 xianyu task actions; None otherwise.
    catalog_id: str | None = None
    # Registration status of the production execution lane for this action.
    # "executable" only when a deployed lane can mint/execute today.
    availability: OperationAvailability = "executable"
    # Why the action is not executable yet (required when availability !=
    # "executable"): the prerequisite that must land first.
    prerequisite: str = ""

    def __post_init__(self) -> None:
        if not self.result_type:
            raise ValueError(f"operation {self.key} must declare a result_type")
        if self.availability != "executable" and not self.prerequisite:
            raise ValueError(
                f"operation {self.key} must declare a prerequisite when it is {self.availability}"
            )


FeatureMode = Literal["guide", "table", "form", "assets", "insight", "settings"]
FeatureRisk = Literal["standard", "approval", "blocked"]
FeatureExecutionState = Literal["implemented", "contract_only", "ui_only", "blocked"]


@dataclass(frozen=True, slots=True)
class FeatureModuleDefinition:
    id: str
    label: str
    stage: str
    titles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    id: str
    index: int
    module: str
    module_label: str
    stage: str
    title: str
    mode: FeatureMode
    risk: FeatureRisk
    operation_key: str | None
    policy: Literal["mapped", "unmapped", "blocked"]
    execution_state: FeatureExecutionState
    reason: str


DEFINITIONS = (
    OperationDefinition(
        "accounts.authorization.health_check",
        "accounts",
        "account",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"checks"}),
        "Validate recorded authorization and binding health without collecting credentials.",
        result_type="AccountHealthReportResult",
    ),
    OperationDefinition(
        "devices.capabilities.refresh",
        "devices",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"includeApps"}),
        "Refresh the safe device capability inventory through Edge.",
        result_type="DeviceCapabilityInventoryResult",
    ),
    OperationDefinition(
        "groups.membership.reindex",
        "groups",
        "content_group",
        Permission.CONTENT_WRITE,
        True,
        frozenset({"dryRun"}),
        "Rebuild content group membership indexes without modifying frozen snapshots.",
        result_type="GroupMembershipIndexResult",
    ),
    OperationDefinition(
        "media.derivative.generate",
        "media",
        "media_asset",
        Permission.CONTENT_WRITE,
        True,
        frozenset({"derivativeProfileId"}),
        "Generate traceable media derivatives while retaining the original object.",
        result_type="MediaDerivativeGeneratedResult",
    ),
    OperationDefinition(
        "watermarks.preview.render",
        "watermarks",
        "media_asset",
        Permission.CONTENT_WRITE,
        True,
        frozenset({"ruleVersionId"}),
        "Render a non-destructive watermark preview.",
        result_type="WatermarkPreviewRenderedResult",
    ),
    OperationDefinition(
        "works.revision.validate",
        "works",
        "content_revision",
        Permission.CONTENT_WRITE,
        True,
        frozenset({"policyVersion"}),
        "Validate immutable work revisions against content policy.",
        result_type="WorkRevisionValidatedResult",
    ),
    OperationDefinition(
        "publish_plans.snapshot.validate",
        "publish_plans",
        "publish_plan",
        Permission.PUBLISH_CREATE,
        True,
        frozenset({"strict"}),
        "Validate frozen snapshots without scheduling or controlling devices.",
        "approval",
        result_type="PublishSnapshotValidatedResult",
    ),
    OperationDefinition(
        "xianyu.listing.publish",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        False,
        frozenset({"listingBody", "price", "mediaAssetIds", "productId"}),
        "Dispatch an idlefish text listing form-fill task to the enrolled Companion.",
        result_type="XianyuPublishListingResult",
        catalog_id="xy-tasks-01",
        availability="executable",
    ),
    OperationDefinition(
        "task_runs.evidence.export",
        "task_runs",
        "task_run",
        Permission.PUBLISH_READ,
        True,
        frozenset({"format", "redact"}),
        "Export tenant-scoped evidence indexes with mandatory redaction support.",
        result_type="TaskEvidenceExportResult",
    ),
    OperationDefinition(
        "automation_packages.qualification.run",
        "automation_packages",
        "automation_package_version",
        Permission.AUTOMATION_MANAGE,
        True,
        frozenset({"matrixProfile"}),
        "Run qualification against an approved compatibility matrix.",
        result_type="QualificationRunReportResult",
    ),
    OperationDefinition(
        "debug_sessions.evidence.export",
        "debug_sessions",
        "debug_session",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"format"}),
        "Export audited debug-session evidence without exposing device credentials.",
        result_type="DebugEvidenceExportResult",
    ),
    OperationDefinition(
        "apk_artifacts.analysis.run",
        "apk_artifacts",
        "apk_artifact",
        Permission.APK_MANAGE,
        True,
        frozenset({"scanners"}),
        "Run malware, permission, signature, and SBOM analysis.",
        result_type="ApkArtifactAnalysisResult",
    ),
    OperationDefinition(
        "apk_rollouts.health_check",
        "apk_rollouts",
        "apk_rollout",
        Permission.APK_MANAGE,
        True,
        frozenset({"observationWindowSeconds"}),
        "Check rollout health without starting installation or bypassing package policy.",
        result_type="ApkRolloutHealthReportResult",
    ),
    OperationDefinition(
        "security_policies.export",
        "security_policies",
        "security_policy",
        Permission.TENANT_ADMIN,
        False,
        frozenset({"format"}),
        "Export the effective tenant security policy without secret material.",
        result_type="SecurityPolicyExportResult",
    ),
    OperationDefinition(
        "users_roles.access_review.generate",
        "users_roles",
        "user",
        Permission.TENANT_ADMIN,
        True,
        frozenset({"scope"}),
        "Generate an access review without changing role assignments.",
        result_type="AccessReviewReportResult",
    ),
    OperationDefinition(
        "audit_exports.generate",
        "audit_exports",
        "audit_event",
        Permission.AUDIT_READ,
        False,
        frozenset({"from", "to", "format"}),
        "Generate a tenant-scoped immutable audit export.",
        result_type="AuditExportResult",
    ),
)

# ---------------------------------------------------------------------------
# A09: per-action registration of the 31 xianyu (xy-tasks) operations from
# docs/phase1/field-map.json. Keys reuse the frozen field-map commandType
# identity where one exists; xy-tasks-01 keeps its pre-existing catalog key
# (xianyu.listing.publish, the A05 mint lane target).
#
# Result identity red line: every action carries its own result_type that
# names what the action actually did (polish / deleted / price updated /
# review posted / promote started / ...). Deletions of different resources
# (goods / posts / feed / messages / comments) are distinct result types.
# Shared-service pages (pools / watermark) register their shared-lane use
# without minting device commands.
# ---------------------------------------------------------------------------

_T102 = (
    "T102 real-device verification required (field-map {catalog_id} AVAILABILITY_PENDING): "
    "the Xianyu surface for this action must be verified on authorized hardware before "
    "any executor can be declared."
)
_NO_COMMAND_V1 = (
    "No production CommandV1 type exists for this action (K05 frozen closed CommandType "
    "enum); minting stays fail-closed until an executor command type is delivered and "
    "five-way synced per platform-recipe/v1 §2."
)
_POLICY_BLOCKED = (
    "Production policy blocks this feature (BLOCKED_FEATURE_IDS: coin/review engagement "
    "actions are prohibited, repository rule 7); catalogued for inventory only and the "
    "feature stays blocked even though the operation contract is registered."
)

XY_TASK_DEFINITIONS: tuple[OperationDefinition, ...] = (
    # xy-tasks-02 发布帖子 — AVAILABILITY_PENDING, must not be silently removed.
    OperationDefinition(
        "xianyu.publish_post",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        False,
        frozenset(),
        "Publish a Xianyu post (fish circle) on the bound account's device.",
        "approval",
        result_type="XianyuPublishPostResult",
        catalog_id="xy-tasks-02",
        availability="pending_device_verification",
        prerequisite=_T102.format(catalog_id="xy-tasks-02"),
    ),
    # xy-tasks-03 擦亮商品
    OperationDefinition(
        "xianyu.polish_goods",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"intervalSeconds", "schedule"}),
        "Re-polish (bump) listings on the bound account's device on an interval.",
        "approval",
        result_type="XianyuPolishGoodsResult",
        catalog_id="xy-tasks-03",
        availability="contract_only",
        prerequisite=_NO_COMMAND_V1,
    ),
    # xy-tasks-04 上架商品
    OperationDefinition(
        "xianyu.shelf_up",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"intervalSeconds"}),
        "Put shelf-down listings back on sale on the bound account's device.",
        "approval",
        result_type="XianyuShelfUpResult",
        catalog_id="xy-tasks-04",
        availability="contract_only",
        prerequisite=_NO_COMMAND_V1,
    ),
    # xy-tasks-05 下架商品
    OperationDefinition(
        "xianyu.shelf_down",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"exposure", "views", "wants", "keyword"}),
        "Take listings off sale when they match exposure/view/want/keyword filters.",
        "approval",
        result_type="XianyuShelfDownResult",
        catalog_id="xy-tasks-05",
        availability="contract_only",
        prerequisite=_NO_COMMAND_V1,
    ),
    # xy-tasks-06 删除商品
    OperationDefinition(
        "xianyu.delete_goods",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"target"}),
        "Delete listings matching the declared target selection on the device.",
        "approval",
        result_type="XianyuGoodsDeletedResult",
        catalog_id="xy-tasks-06",
        availability="contract_only",
        prerequisite=_NO_COMMAND_V1,
    ),
    # xy-tasks-07 删除帖子 — AVAILABILITY_PENDING, must not be silently removed.
    OperationDefinition(
        "xianyu.delete_post",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset(),
        "Delete previously published Xianyu posts on the bound account's device.",
        "approval",
        result_type="XianyuPostDeletedResult",
        catalog_id="xy-tasks-07",
        availability="pending_device_verification",
        prerequisite=_T102.format(catalog_id="xy-tasks-07"),
    ),
    # xy-tasks-08 绑定闲鱼
    OperationDefinition(
        "xianyu.bind_account",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"memberName"}),
        "Bind the enrolled device to the declared Xianyu member identity.",
        "approval",
        result_type="XianyuAccountBoundResult",
        catalog_id="xy-tasks-08",
        availability="contract_only",
        prerequisite=_NO_COMMAND_V1,
    ),
    # xy-tasks-09 签到鱼币 — production-policy blocked feature.
    OperationDefinition(
        "xianyu.checkin_coins",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"jumpTask"}),
        "Perform the Xianyu daily coin check-in (feature blocked by production policy).",
        "approval",
        result_type="XianyuCoinCheckinResult",
        catalog_id="xy-tasks-09",
        availability="contract_only",
        prerequisite=_POLICY_BLOCKED,
    ),
    # xy-tasks-10 鱼币抵扣 — production-policy blocked feature.
    OperationDefinition(
        "xianyu.coin_discount",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"dikouType", "dikouTarget", "intervalSeconds"}),
        "Apply coin deduction offers to eligible orders (feature blocked by production policy).",
        "approval",
        result_type="XianyuCoinDiscountAppliedResult",
        catalog_id="xy-tasks-10",
        availability="contract_only",
        prerequisite=_POLICY_BLOCKED,
    ),
    # xy-tasks-11 鱼币推广 — production-policy blocked feature; budget fields are
    # declared Literals so any budget drift fails validation.
    OperationDefinition(
        "xianyu.coin_promote",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"promoteItem", "promotePackage"}),
        "Spend coins on listing promotion packages (feature blocked by production policy).",
        "approval",
        result_type="XianyuCoinPromoteStartedResult",
        catalog_id="xy-tasks-11",
        availability="contract_only",
        prerequisite=_POLICY_BLOCKED,
    ),
    # xy-tasks-12 一键小刀
    OperationDefinition(
        "xianyu.bargain",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"xiaodaoType", "privateMessage"}),
        "Offer small bargaining discounts to interested buyers on the device.",
        "approval",
        result_type="XianyuBargainOfferedResult",
        catalog_id="xy-tasks-12",
        availability="contract_only",
        prerequisite=_NO_COMMAND_V1,
    ),
    # xy-tasks-13 一键降价
    OperationDefinition(
        "xianyu.price_cut",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"percentCut", "amountCut", "target"}),
        "Cut listing prices by a declared percent or fixed amount.",
        "approval",
        result_type="XianyuPriceUpdatedResult",
        catalog_id="xy-tasks-13",
        availability="contract_only",
        prerequisite=_NO_COMMAND_V1,
    ),
    # xy-tasks-14 一键好评 — production-policy blocked feature.
    OperationDefinition(
        "xianyu.review",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"reviewBody", "reviewTarget"}),
        "Post reviews to buyers on the device (feature blocked by production policy).",
        "approval",
        result_type="XianyuReviewPostedResult",
        catalog_id="xy-tasks-14",
        availability="contract_only",
        prerequisite=_POLICY_BLOCKED,
    ),
    # xy-tasks-15 重启闲鱼 — plain APKs cannot guarantee a process kill; failures
    # must surface a reasonCode.
    OperationDefinition(
        "xianyu.restart_app",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset(),
        "Restart the Xianyu app on the device; failures must report a reasonCode.",
        "approval",
        result_type="XianyuAppRestartedResult",
        catalog_id="xy-tasks-15",
        availability="contract_only",
        prerequisite=_NO_COMMAND_V1,
    ),
    # xy-tasks-16 删除动态
    OperationDefinition(
        "xianyu.delete_feed",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"quantity"}),
        "Delete the account's feed items up to the declared quantity.",
        "approval",
        result_type="XianyuFeedDeletedResult",
        catalog_id="xy-tasks-16",
        availability="contract_only",
        prerequisite=_NO_COMMAND_V1,
    ),
    # xy-tasks-17 删除消息
    OperationDefinition(
        "xianyu.delete_message",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"messageAction"}),
        "Delete chat messages according to the declared message action.",
        "approval",
        result_type="XianyuMessageDeletedResult",
        catalog_id="xy-tasks-17",
        availability="contract_only",
        prerequisite=_NO_COMMAND_V1,
    ),
    # xy-tasks-18 删除留言
    OperationDefinition(
        "xianyu.delete_comment",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"quantity"}),
        "Delete listing comments up to the declared quantity.",
        "approval",
        result_type="XianyuCommentDeletedResult",
        catalog_id="xy-tasks-18",
        availability="contract_only",
        prerequisite=_NO_COMMAND_V1,
    ),
    # xy-tasks-19 草稿上架
    OperationDefinition(
        "xianyu.draft_publish",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset(),
        "Publish listings sitting in the account's Xianyu drafts.",
        "approval",
        result_type="XianyuDraftRelistedResult",
        catalog_id="xy-tasks-19",
        availability="contract_only",
        prerequisite=_NO_COMMAND_V1,
    ),
    # xy-tasks-20 编辑重发
    OperationDefinition(
        "xianyu.reedit",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"intervalSeconds", "addressPool"}),
        "Edit and re-publish listings on an interval, optionally rotating pool addresses.",
        "approval",
        result_type="XianyuReeditRelistedResult",
        catalog_id="xy-tasks-20",
        availability="contract_only",
        prerequisite=_NO_COMMAND_V1,
    ),
    # xy-tasks-21 托管无忧卖
    OperationDefinition(
        "xianyu.wuyoumai",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"wuyoumaiType"}),
        "Enable the declared Wuyoumai hosting tier on listings.",
        "approval",
        result_type="XianyuWuyoumaiEnabledResult",
        catalog_id="xy-tasks-21",
        availability="contract_only",
        prerequisite=_NO_COMMAND_V1,
    ),
    # xy-tasks-22 快速编辑重发
    OperationDefinition(
        "xianyu.fast_reedit",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"autoShortTitle"}),
        "Quick edit-and-republish with optional automatic short titles.",
        "approval",
        result_type="XianyuFastReeditRelistedResult",
        catalog_id="xy-tasks-22",
        availability="contract_only",
        prerequisite=_NO_COMMAND_V1,
    ),
    # xy-tasks-23 快速下架商品
    OperationDefinition(
        "xianyu.fast_shelf_down",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset(),
        "Take all on-sale listings down in one quick pass.",
        "approval",
        result_type="XianyuFastShelfDownResult",
        catalog_id="xy-tasks-23",
        availability="contract_only",
        prerequisite=_NO_COMMAND_V1,
    ),
    # xy-tasks-24 采集宝贝信息 — read-only collection, shared with analytics.
    OperationDefinition(
        "xianyu.collect_listings",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset(),
        "Collect own-listing analytics snapshots on the bound account's device.",
        result_type="XianyuListingsCollectedResult",
        catalog_id="xy-tasks-24",
        availability="contract_only",
        prerequisite=_NO_COMMAND_V1,
    ),
    # xy-tasks-25/26 通用/设备地址池 — shared address-pool service pages.
    OperationDefinition(
        "xianyu.shared.generic_address_pool",
        "xy_tasks",
        "address_pool",
        Permission.CONTENT_WRITE,
        True,
        frozenset(),
        "Generic address pool management entry on the xy-tasks module (shared service).",
        result_type="GenericAddressPoolUpdatedResult",
        catalog_id="xy-tasks-25",
        availability="contract_only",
        prerequisite=(
            "Shared address-pool service (product-editor/assets lanes own the pool "
            "contract); this entry only registers the xy-tasks page's use of it."
        ),
    ),
    OperationDefinition(
        "xianyu.shared.device_address_pool",
        "xy_tasks",
        "address_pool",
        Permission.CONTENT_WRITE,
        True,
        frozenset(),
        "Per-device address pool management entry on the xy-tasks module (shared service).",
        result_type="DeviceAddressPoolUpdatedResult",
        catalog_id="xy-tasks-26",
        availability="contract_only",
        prerequisite=(
            "Shared address-pool service (product-editor/assets lanes own the pool "
            "contract); this entry only registers the xy-tasks page's use of it."
        ),
    ),
    # xy-tasks-27 描述池
    OperationDefinition(
        "xianyu.shared.description_pool",
        "xy_tasks",
        "description_pool",
        Permission.CONTENT_WRITE,
        True,
        frozenset(),
        "Description pool management entry on the xy-tasks module (shared service).",
        result_type="DescriptionPoolUpdatedResult",
        catalog_id="xy-tasks-27",
        availability="contract_only",
        prerequisite=(
            "Shared description-pool service (product-editor/assets lanes own the pool "
            "contract); this entry only registers the xy-tasks page's use of it."
        ),
    ),
    # xy-tasks-28 标签池
    OperationDefinition(
        "xianyu.shared.tag_pool",
        "xy_tasks",
        "tag_pool",
        Permission.CONTENT_WRITE,
        True,
        frozenset(),
        "Tag pool management entry on the xy-tasks module (shared service).",
        result_type="TagPoolUpdatedResult",
        catalog_id="xy-tasks-28",
        availability="contract_only",
        prerequisite=(
            "Shared tag-pool service (product-editor/assets lanes own the pool "
            "contract); this entry only registers the xy-tasks page's use of it."
        ),
    ),
    # xy-tasks-29 图片水印
    OperationDefinition(
        "xianyu.shared.watermark",
        "xy_tasks",
        "media_asset",
        Permission.CONTENT_WRITE,
        True,
        frozenset({"ruleVersionId"}),
        "Image watermark entry on the xy-tasks module (shared watermark service).",
        result_type="XianyuWatermarkRenderedResult",
        catalog_id="xy-tasks-29",
        availability="contract_only",
        prerequisite=(
            "Shared watermark service (watermarks.preview.render lane owns the render "
            "contract); this entry only registers the xy-tasks page's use of it."
        ),
    ),
    # xy-tasks-30 违禁词检测 — server-side scan, no device command.
    OperationDefinition(
        "content.forbidden_words.scan",
        "xy_tasks",
        "content_revision",
        Permission.CONTENT_WRITE,
        True,
        frozenset({"policyVersion"}),
        "Scan frozen content revisions for forbidden words against a policy version.",
        result_type="ForbiddenWordsScanResult",
        catalog_id="xy-tasks-30",
        availability="contract_only",
        prerequisite=(
            "Server-side scan lane is not wired to an operations executor yet; the "
            "works.revision.validate lane carries the deployed validation contract."
        ),
    ),
    # xy-tasks-31 视频操作教程 — guide-only page, registered for inventory parity.
    OperationDefinition(
        "xianyu.guide.videos",
        "xy_tasks",
        "feature_guide",
        Permission.CONTENT_READ,
        False,
        frozenset(),
        "Video operation guide page; guide-only inventory with no execution semantics.",
        result_type="VideoGuideContentResult",
        catalog_id="xy-tasks-31",
        availability="contract_only",
        prerequisite="Guide-only page: tutorial video inventory, no backend operation.",
    ),
)

DEFINITIONS = (*DEFINITIONS, *XY_TASK_DEFINITIONS)

BY_KEY = {definition.key: definition for definition in DEFINITIONS}
BY_CATALOG_ID: dict[str, OperationDefinition] = {
    definition.catalog_id: definition for definition in DEFINITIONS if definition.catalog_id
}
XY_TASK_CATALOG_IDS = tuple(f"xy-tasks-{index:02d}" for index in range(1, 32))
if set(BY_CATALOG_ID) != set(XY_TASK_CATALOG_IDS):
    raise ValueError("every xy-tasks-01..31 action must be registered exactly once")

# field-map xy-tasks actions whose AVAILABILITY_PENDING status is preserved as
# pending_device_verification (T102 real-device verification prerequisite).
XY_PENDING_DEVICE_VERIFICATION_IDS = frozenset(
    catalog_id
    for catalog_id in XY_TASK_CATALOG_IDS
    if BY_CATALOG_ID[catalog_id].availability == "pending_device_verification"
)

# The supplied competitor report contains 134 stable feature entries.  This metadata is
# requirement inventory only: it never grants permission or implies an executor exists.
FEATURE_MODULES = (
    FeatureModuleDefinition(
        "system-home",
        "系统主页",
        "数据复盘",
        (
            "产品介绍",
            "设备列表",
            "系统授权",
            "常见问题",
            "常用工具",
            "更新日志",
            "超级擦亮",
            "建议反馈",
            "公告通知",
            "视频教程",
        ),
    ),
    FeatureModuleDefinition("task-queue", "任务队列", "分发执行", ("任务队列",)),
    FeatureModuleDefinition(
        "product-editor",
        "产品编辑",
        "内容生产",
        (
            "普通宝贝",
            "拍卖宝贝",
            "宝贝水印",
            "通用地址池",
            "设备地址池",
            "宝贝描述池",
            "宝贝标签池",
            "房屋出租",
            "免费送宝贝",
            "视频操作教程",
        ),
    ),
    FeatureModuleDefinition(
        "collection",
        "采集管理",
        "资产准备",
        (
            "商品链接采集",
            "闲鱼店铺解析",
            "搜索闲鱼宝贝",
            "淘宝店铺解析",
            "转转店铺解析",
            "微商相册解析",
            "孔网店铺解析",
            "阿里巴巴解析",
            "宝贝详情解析",
            "宝贝视频解析",
            "文章链接采集",
            "多多宝贝采集",
            "采集任务列表",
            "视频操作教程",
        ),
    ),
    FeatureModuleDefinition(
        "product-management",
        "商品管理",
        "内容生产",
        (
            "商品列表",
            "商品导入",
            "商品分组",
            "货源共享",
            "发布闲鱼",
            "发布转转",
            "多多数据包",
            "淘宝数据包",
            "违禁词检测",
            "视频操作教程",
        ),
    ),
    FeatureModuleDefinition(
        "post-management",
        "帖子管理",
        "内容生产",
        (
            "帖子编辑",
            "帖子采集",
            "帖子列表",
            "帖子分组",
            "帖子水印",
            "删除帖子",
            "发布闲鱼",
            "发布小红书",
            "视频教程",
        ),
    ),
    FeatureModuleDefinition(
        "orders",
        "订单管理",
        "互动交易",
        ("同步闲鱼订单", "去拼多多采购", "取拼多多单号", "查看全部订单", "视频操作教程"),
    ),
    FeatureModuleDefinition(
        "analytics",
        "统计分析",
        "数据复盘",
        ("采集宝贝信息", "宝贝流量变化", "视频操作教程"),
    ),
    FeatureModuleDefinition(
        "xy-tasks",
        "闲鱼授权任务",
        "分发执行",
        (
            "发布商品",
            "发布帖子",
            "擦亮商品",
            "上架商品",
            "下架商品",
            "删除商品",
            "删除帖子",
            "绑定闲鱼",
            "签到鱼币",
            "鱼币抵扣",
            "鱼币推广",
            "一键小刀",
            "一键降价",
            "一键好评",
            "重启闲鱼",
            "删除动态",
            "删除消息",
            "删除留言",
            "草稿上架",
            "编辑重发",
            "托管无忧卖",
            "快速编辑重发",
            "快速下架商品",
            "采集宝贝信息",
            "通用地址池",
            "设备地址池",
            "描述池",
            "标签池",
            "图片水印",
            "违禁词检测",
            "视频操作教程",
        ),
    ),
    FeatureModuleDefinition(
        "zz-tasks",
        "转转授权任务",
        "分发执行",
        (
            "发布商品",
            "擦亮商品",
            "下架商品",
            "上架商品",
            "删除商品",
            "转转养号",
            "流量模式",
            "违禁词检测",
            "视频操作教程",
        ),
    ),
    FeatureModuleDefinition(
        "red-tasks",
        "小红书授权任务",
        "分发执行",
        ("发布笔记", "删除笔记", "小红书养号", "搜索养号"),
    ),
    FeatureModuleDefinition(
        "creative",
        "创意中心",
        "内容生产",
        ("爆款商品分析", "创意文案", "TOP5000蓝海词", "视频教程"),
    ),
    FeatureModuleDefinition(
        "chat",
        "聊天管理",
        "互动交易",
        (
            "开启消息回复",
            "关闭消息回复",
            "关键词回复",
            "场景回复组",
            "手机端回复",
            "消息回复格式",
            "快捷回复管理",
            "表情素材管理",
            "图片素材管理",
            "音频素材管理",
            "视频素材管理",
        ),
    ),
    FeatureModuleDefinition(
        "assets",
        "系统素材",
        "资产准备",
        (
            "图片水印",
            "图片素材",
            "音频素材",
            "视频素材",
            "通用地址池",
            "设备地址池",
            "描述池",
            "标签池",
        ),
    ),
    FeatureModuleDefinition(
        "profile",
        "个人中心",
        "数据复盘",
        ("基本资料", "修改密码", "邀请好友", "积分明细", "AI功能设置"),
    ),
)
FEATURE_MODULE_COUNTS = tuple((module.id, len(module.titles)) for module in FEATURE_MODULES)
FEATURE_OPERATION_MAP: dict[str, str | None] = {
    f"{module}-{index:02d}": None
    for module, count in FEATURE_MODULE_COUNTS
    for index in range(1, count + 1)
}
FEATURE_OPERATION_MAP.update(
    {
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
    }
)
# A09: every xy-tasks feature maps to its per-action registration. xy-tasks-02
# previously pointed at the publish_plans.snapshot.validate validation gate;
# after A09 it points at its own pending registration (T102 prerequisite),
# preserving the AVAILABILITY_PENDING action instead of a placeholder.
FEATURE_OPERATION_MAP.update(
    {catalog_id: BY_CATALOG_ID[catalog_id].key for catalog_id in XY_TASK_CATALOG_IDS}
)

BLOCKED_FEATURE_IDS = frozenset(
    {
        *(f"collection-{index:02d}" for index in range(1, 13)),
        "orders-02",
        "orders-03",
        "xy-tasks-09",
        "xy-tasks-10",
        "xy-tasks-11",
        "xy-tasks-14",
        "zz-tasks-06",
        "zz-tasks-07",
        "red-tasks-03",
        "red-tasks-04",
    }
)

# ---------------------------------------------------------------------------
# X12 (fleet-first-20260916.1, task card "31项操作目录的范围和可用性收口"):
# four-state availability ledger for the 31 xy-tasks actions. Registration in
# XY_TASK_DEFINITIONS is inventory, never an enablement: every action carries
# exactly one ledger state with a reason that is surfaced to the UI through
# the /api/v1/operations/features `reason` field (prefixed "[STATE] ...").
#
# States (derived from the registrations — never hand-set per row):
#   ENABLED        a deployed production lane can execute it today
#                  (xy-tasks-01 only; cross-checked against
#                  operation_runtime.BUILTIN_OPERATION_KEYS by tests).
#   PENDING        in scope, missing a prerequisite: production CommandV1
#                  lane, T102 real-device verification, and/or the sensitive
#                  evidence discipline (budget cap / target authorization /
#                  pinned-version platform entry evidence).
#   POLICY_BLOCKED production policy prohibits the feature (repository rule
#                  7: coin/review engagement). Evidence can never flip this;
#                  only a recorded policy decision can.
#   OUT_OF_SCOPE   adjudicated scope change (shared-service pages owned by
#                  other lanes, guide-only inventory): never an executor
#                  target for the xy device lane.
#
# The machine-readable twin of this ledger is
# docs/current/operation-availability.json (single-sourced here; the contract
# test asserts byte-level parity of the entries).
# ---------------------------------------------------------------------------

LedgerState = Literal["ENABLED", "PENDING", "POLICY_BLOCKED", "OUT_OF_SCOPE"]
LEDGER_STATES: tuple[str, ...] = ("ENABLED", "PENDING", "POLICY_BLOCKED", "OUT_OF_SCOPE")

# Evidence keys a PENDING row may require before an ENABLED transition is even
# considered (see evaluate_ledger_transition; the deployed executor gate is
# always evaluated independently and additionally).
LEDGER_EVIDENCE_KEYS = frozenset(
    {
        "command_v1_lane",
        "t102_verification",
        "budget_cap",
        "target_authorization",
        "platform_entry_evidence",
        "scan_executor_wiring",
    }
)

# xy-tasks rows adjudicated out of scope for the xy device lane (X12): the
# shared pool/watermark contracts are owned by the product-editor/assets
# lanes, and the video tutorial page is guide-only inventory.
XY_OUT_OF_SCOPE_IDS = frozenset(
    {
        "xy-tasks-25",
        "xy-tasks-26",
        "xy-tasks-27",
        "xy-tasks-28",
        "xy-tasks-29",
        "xy-tasks-31",
    }
)

# X12 task card: coin spend, promotion, review, and message-deletion class
# actions carry the sensitive discipline (budget cap / target authorization /
# pinned-version platform entry evidence). Unverified rows stay disabled.
XY_SENSITIVE_IDS = frozenset(
    {
        "xy-tasks-09",
        "xy-tasks-10",
        "xy-tasks-11",
        "xy-tasks-14",
        "xy-tasks-16",
        "xy-tasks-17",
        "xy-tasks-18",
    }
)

XY_POLICY_BLOCKED_IDS = frozenset(
    catalog_id for catalog_id in XY_TASK_CATALOG_IDS if catalog_id in BLOCKED_FEATURE_IDS
)

# Task/package references (docs/current/tasks.json, plan fleet-first-20260916.1):
# X11 维护操作按身份逐件执行 → P29,P31,P33,P35,P37; X10 P09删除专项 →
# P30,P32,P34,P36,P38,P39; P46 integration lane; P49 platform-scope
# verification package. Policy-blocked rows cite every device lane because all
# of them must keep the capability disabled.
_X11_PACKAGES = ("P29", "P31", "P33", "P35", "P37")
_X10_PACKAGES = ("P30", "P32", "P34", "P36", "P38", "P39")
_ALL_DEVICE_PACKAGES = tuple(f"P{index:02d}" for index in range(29, 40))
_SHARED_SERVICE_PACKAGES = ("P46", "P49")

_LEDGER_ENABLED_REASON = (
    "Deployed open-only publish lane: CommandV1 xianyu.publish_listing.v1 is a "
    "PRODUCTION_ALIASES mint target and the mobile task dispatch lane executes it; "
    "result identity stays open-only (reached_confirmation_point + evidence ref)."
)
_LEDGER_OUT_OF_SCOPE_REASONS = {
    "xy-tasks-25": (
        "Scope change recorded by X12: the xy-tasks generic address-pool page only "
        "consumes the shared address-pool service owned by the product-editor/assets "
        "lanes; this row will never mint a xy device operation."
    ),
    "xy-tasks-26": (
        "Scope change recorded by X12: the xy-tasks per-device address-pool page only "
        "consumes the shared address-pool service owned by the product-editor/assets "
        "lanes; this row will never mint a xy device operation."
    ),
    "xy-tasks-27": (
        "Scope change recorded by X12: the description-pool contract is owned by the "
        "product-editor/assets lanes; this row only registers the xy-tasks page's use "
        "of that shared service."
    ),
    "xy-tasks-28": (
        "Scope change recorded by X12: the tag-pool contract is owned by the "
        "product-editor/assets lanes; this row only registers the xy-tasks page's use "
        "of that shared service."
    ),
    "xy-tasks-29": (
        "Scope change recorded by X12: the watermark render contract is owned by the "
        "watermarks.preview.render lane; this row only registers the xy-tasks page's "
        "use of that shared service."
    ),
    "xy-tasks-31": (
        "Scope change recorded by X12: guide-only tutorial inventory with no execution "
        "semantics; registered for 31-action parity, never an executor target."
    ),
}
_LEDGER_SENSITIVE_ADDENDUM = (
    " X12 sensitive category (coin spend / promotion / review / message deletion): "
    "budget cap, target authorization, and pinned-version platform entry evidence "
    "are unverified; the row stays disabled until all three are recorded."
)


@dataclass(frozen=True, slots=True)
class SensitiveDiscipline:
    """X12 evidence discipline for engagement/deletion-class actions."""

    budget_cap: str
    target_authorization: str
    platform_entry_evidence: str


@dataclass(frozen=True, slots=True)
class AvailabilityLedgerEntry:
    """One xy-tasks action in the X12 four-state availability ledger."""

    catalog_id: str
    operation_key: str
    title: str
    state: LedgerState
    reason: str
    task_refs: tuple[str, ...]
    package_refs: tuple[str, ...]
    enable_requires: tuple[str, ...]
    sensitive: SensitiveDiscipline | None = None


_LEDGER_SENSITIVE: dict[str, SensitiveDiscipline] = {
    "xy-tasks-09": SensitiveDiscipline(
        budget_cap=(
            "N/A — the daily check-in accrues coins and has no spend knob; no "
            "coin-spend budget is approved for this tenant."
        ),
        target_authorization=(
            "Own bound account only (device-enrolled member identity; "
            "DEVICE_MAINTAIN permission plus approval risk gate)."
        ),
        platform_entry_evidence=(
            "unverified — the Xianyu coin check-in entry must be captured on the "
            "pinned app version (7.18.92) on authorized hardware."
        ),
    ),
    "xy-tasks-10": SensitiveDiscipline(
        budget_cap=(
            "None approved — deduction tiers are closed Literals (dikouType: "
            "order_fees/postage) but no tenant coin-spend budget exists."
        ),
        target_authorization=(
            "dikouTarget closed Literal (all_eligible/manually_selected); only "
            "orders owned by the bound account."
        ),
        platform_entry_evidence=(
            "unverified — the deduction-offer surface has not been captured on the "
            "pinned app version (7.18.92)."
        ),
    ),
    "xy-tasks-11": SensitiveDiscipline(
        budget_cap=(
            "None approved — promotion packages are closed Literals "
            "(coins_60/coins_120/coins_300/coins_600) but no per-tenant promotion "
            "budget or ceiling is registered."
        ),
        target_authorization=(
            "promoteItem closed Literal (manually_selected/recently_listed); "
            "promotion may only target the bound account's own listings."
        ),
        platform_entry_evidence=(
            "unverified — the promotion purchase flow has not been captured on the "
            "pinned app version (7.18.92)."
        ),
    ),
    "xy-tasks-14": SensitiveDiscipline(
        budget_cap=(
            "None approved — no review-volume cap is registered."
        ),
        target_authorization=(
            "reviewTarget closed Literal (recent_buyers/all_unreviewed); requires a "
            "buyer relationship with the bound account."
        ),
        platform_entry_evidence=(
            "unverified — the review composition/post surface has not been captured "
            "on the pinned app version (7.18.92)."
        ),
    ),
    "xy-tasks-16": SensitiveDiscipline(
        budget_cap=(
            "quantity is bounded to 1..100 per run; no recurring-volume budget is "
            "approved."
        ),
        target_authorization=(
            "Own-account feed items only; no third-party content."
        ),
        platform_entry_evidence=(
            "unverified — the feed deletion surface has not been captured on the "
            "pinned app version (7.18.92)."
        ),
    ),
    "xy-tasks-17": SensitiveDiscipline(
        budget_cap=(
            "N/A — action-scoped (messageAction: clear_all/older_than_7_days), no "
            "volume knob; a per-run confirmation is still required."
        ),
        target_authorization=(
            "Own chat messages only; the messageAction closed Literal must match the "
            "declared scope."
        ),
        platform_entry_evidence=(
            "unverified — the chat message deletion surface has not been captured on "
            "the pinned app version (7.18.92)."
        ),
    ),
    "xy-tasks-18": SensitiveDiscipline(
        budget_cap=(
            "quantity is bounded to 1..100 per run; no recurring-volume budget is "
            "approved."
        ),
        target_authorization=(
            "Comments on the bound account's own listings only."
        ),
        platform_entry_evidence=(
            "unverified — the comment deletion surface has not been captured on the "
            "pinned app version (7.18.92)."
        ),
    ),
}

_XY_TITLES = (
    "发布商品",
    "发布帖子",
    "擦亮商品",
    "上架商品",
    "下架商品",
    "删除商品",
    "删除帖子",
    "绑定闲鱼",
    "签到鱼币",
    "鱼币抵扣",
    "鱼币推广",
    "一键小刀",
    "一键降价",
    "一键好评",
    "重启闲鱼",
    "删除动态",
    "删除消息",
    "删除留言",
    "草稿上架",
    "编辑重发",
    "托管无忧卖",
    "快速编辑重发",
    "快速下架商品",
    "采集宝贝信息",
    "通用地址池",
    "设备地址池",
    "描述池",
    "标签池",
    "图片水印",
    "违禁词检测",
    "视频操作教程",
)

_DELETION_IDS = frozenset(
    {"xy-tasks-06", "xy-tasks-07", "xy-tasks-16", "xy-tasks-17", "xy-tasks-18"}
)


def _ledger_refs(catalog_id: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if catalog_id in XY_POLICY_BLOCKED_IDS:
        return ("X12",), _ALL_DEVICE_PACKAGES
    if catalog_id in XY_OUT_OF_SCOPE_IDS:
        return ("X12",), _SHARED_SERVICE_PACKAGES
    if catalog_id == "xy-tasks-30":
        return ("X12",), ("P46",)
    if catalog_id == "xy-tasks-01":
        # The deployed lane is the A05 open-only mint + mobile dispatch lane.
        return ("A05", "X11", "X12"), _X11_PACKAGES
    tasks = ["X12"]
    if catalog_id in XY_PENDING_DEVICE_VERIFICATION_IDS:
        tasks.insert(0, "T102")
    tasks.insert(0, "X10" if catalog_id in _DELETION_IDS else "X11")
    packages = _X10_PACKAGES if catalog_id in _DELETION_IDS else _X11_PACKAGES
    return tuple(tasks), packages


def _ledger_enable_requires(catalog_id: str) -> tuple[str, ...]:
    state = _ledger_state(catalog_id)
    if state in {"POLICY_BLOCKED", "OUT_OF_SCOPE", "ENABLED"}:
        return ()
    requires = ["command_v1_lane"]
    if catalog_id in XY_PENDING_DEVICE_VERIFICATION_IDS:
        requires.insert(0, "t102_verification")
    if catalog_id == "xy-tasks-30":
        requires = ["scan_executor_wiring"]
    elif catalog_id in XY_SENSITIVE_IDS:
        requires.append("target_authorization")
        requires.append("platform_entry_evidence")
        if catalog_id in {"xy-tasks-16", "xy-tasks-18"}:
            requires.append("budget_cap")
    return tuple(requires)


def _ledger_state(catalog_id: str) -> LedgerState:
    if catalog_id in XY_POLICY_BLOCKED_IDS:
        return "POLICY_BLOCKED"
    if catalog_id in XY_OUT_OF_SCOPE_IDS:
        return "OUT_OF_SCOPE"
    if BY_CATALOG_ID[catalog_id].availability == "executable":
        return "ENABLED"
    return "PENDING"


def _build_ledger() -> dict[str, AvailabilityLedgerEntry]:
    ledger: dict[str, AvailabilityLedgerEntry] = {}
    for index, catalog_id in enumerate(XY_TASK_CATALOG_IDS):
        definition = BY_CATALOG_ID[catalog_id]
        state = _ledger_state(catalog_id)
        if state == "ENABLED":
            reason = _LEDGER_ENABLED_REASON
        elif state == "OUT_OF_SCOPE":
            reason = _LEDGER_OUT_OF_SCOPE_REASONS[catalog_id]
        else:
            reason = definition.prerequisite
            if catalog_id in XY_SENSITIVE_IDS:
                reason = f"{reason}{_LEDGER_SENSITIVE_ADDENDUM}"
        task_refs, package_refs = _ledger_refs(catalog_id)
        ledger[catalog_id] = AvailabilityLedgerEntry(
            catalog_id=catalog_id,
            operation_key=definition.key,
            title=_XY_TITLES[index],
            state=state,
            reason=reason,
            task_refs=task_refs,
            package_refs=package_refs,
            enable_requires=_ledger_enable_requires(catalog_id),
            sensitive=_LEDGER_SENSITIVE.get(catalog_id),
        )
    return ledger


XY_AVAILABILITY_LEDGER: dict[str, AvailabilityLedgerEntry] = _build_ledger()
XY_LEDGER_BY_OPERATION_KEY: dict[str, AvailabilityLedgerEntry] = {
    entry.operation_key: entry for entry in XY_AVAILABILITY_LEDGER.values()
}

# Import-time drift guards: the ledger must stay derivable from the
# registrations and the frozen policy sets, and every row must cite the
# ledger-owning task and at least one P package.
if set(XY_AVAILABILITY_LEDGER) != set(XY_TASK_CATALOG_IDS):
    raise ValueError("the X12 availability ledger must cover xy-tasks-01..31 exactly once")
for _catalog_id, _entry in XY_AVAILABILITY_LEDGER.items():
    if _entry.state not in LEDGER_STATES:
        raise ValueError(f"ledger entry {_catalog_id} has an unknown state")
    if _entry.state == "ENABLED" and BY_CATALOG_ID[_catalog_id].availability != "executable":
        raise ValueError(
            f"ledger entry {_catalog_id} is ENABLED without an executable registration"
        )
    if _entry.state == "POLICY_BLOCKED" and _catalog_id not in BLOCKED_FEATURE_IDS:
        raise ValueError(f"ledger entry {_catalog_id} is POLICY_BLOCKED without the feature block")
    if _entry.state == "OUT_OF_SCOPE" and _catalog_id not in XY_OUT_OF_SCOPE_IDS:
        raise ValueError(f"ledger entry {_catalog_id} is OUT_OF_SCOPE without the adjudication")
    if _catalog_id in XY_SENSITIVE_IDS and _entry.state == "ENABLED":
        raise ValueError(f"sensitive ledger entry {_catalog_id} may never be ENABLED")
    if not _entry.enable_requires and _entry.state == "PENDING":
        raise ValueError(f"PENDING ledger entry {_catalog_id} must declare what is missing")
    if _entry.enable_requires and _entry.state != "PENDING":
        raise ValueError(f"non-PENDING ledger entry {_catalog_id} must not declare evidence keys")
    unknown_keys = set(_entry.enable_requires) - LEDGER_EVIDENCE_KEYS
    if unknown_keys:
        raise ValueError(
            f"ledger entry {_catalog_id} declares unknown evidence keys: {unknown_keys}"
        )
    if "X12" not in _entry.task_refs or not _entry.package_refs:
        raise ValueError(f"ledger entry {_catalog_id} must reference task X12 and a P package")
    if _catalog_id in XY_SENSITIVE_IDS and _entry.sensitive is None:
        raise ValueError(f"sensitive ledger entry {_catalog_id} must carry the discipline record")


def evaluate_ledger_transition(
    entry: AvailabilityLedgerEntry,
    evidence: Mapping[str, bool],
    *,
    executor_available: bool,
) -> LedgerState:
    """X12 transition gate: PENDING → ENABLED requires BOTH closed lanes.

    A PENDING row may only flip to ENABLED when every ``enable_requires``
    evidence key is provided AND a deployed executor exists for the action.
    POLICY_BLOCKED and OUT_OF_SCOPE rows are terminal for evidence: a policy
    decision or a new scope adjudication is required, never more evidence.
    Called with no evidence (the default everywhere) every PENDING row stays
    PENDING, which is why "registration" can never silently mean "enabled".
    """
    if entry.state == "POLICY_BLOCKED":
        return "POLICY_BLOCKED"
    if entry.state == "OUT_OF_SCOPE":
        return "OUT_OF_SCOPE"
    if entry.state == "ENABLED":
        return "ENABLED"
    missing = [key for key in entry.enable_requires if not evidence.get(key)]
    if missing or not executor_available:
        return "PENDING"
    return "ENABLED"

GUIDE_TERMS = frozenset({"介绍", "问题", "工具", "日志", "公告", "教程"})
TABLE_TERMS = frozenset({"列表", "队列", "订单", "明细", "变化", "反馈"})
ASSET_TERMS = frozenset({"素材", "水印", "地址池", "描述池", "标签池", "分组", "数据包", "回复组"})
INSIGHT_TERMS = frozenset({"分析", "流量", "TOP5000", "宝贝信息"})
SETTINGS_TERMS = frozenset({"授权", "资料", "密码", "功能设置", "回复格式"})
APPROVAL_TERMS = frozenset(
    {
        "发布",
        "上架",
        "下架",
        "删除",
        "重启",
        "绑定",
        "降价",
        "小刀",
        "擦亮",
        "回复",
        "共享",
        "同步",
        "托管",
        "编辑重发",
        "草稿上架",
    }
)


def _feature_mode(module_id: str, title: str) -> FeatureMode:
    if any(term in title for term in GUIDE_TERMS):
        return "guide"
    if any(term in title for term in INSIGHT_TERMS):
        return "insight"
    if any(term in title for term in ASSET_TERMS):
        return "assets"
    if any(term in title for term in SETTINGS_TERMS):
        return "settings"
    if any(term in title for term in TABLE_TERMS) or module_id == "task-queue":
        return "table"
    return "form"


def _feature_risk(feature_id: str, title: str, operation_key: str | None) -> FeatureRisk:
    if feature_id in BLOCKED_FEATURE_IDS:
        return "blocked"
    if operation_key is not None:
        return BY_KEY[operation_key].risk
    if any(term in title for term in APPROVAL_TERMS):
        return "approval"
    return "standard"


def _feature_state(feature_id: str, operation_key: str | None) -> FeatureExecutionState:
    if feature_id in BLOCKED_FEATURE_IDS:
        return "blocked"
    if operation_key is not None:
        return "contract_only"
    return "ui_only"


def _feature_reason(state: FeatureExecutionState) -> str:
    if state == "blocked":
        return "Production policy prohibits this feature from creating a backend operation."
    if state == "contract_only":
        return (
            "A persisted Operations contract exists, but completion requires an authorized "
            "external executor result callback."
        )
    return "No approved Control API operation or persistence contract is implemented for this page."


_features: list[FeatureDefinition] = []
_feature_index = 0
for _module in FEATURE_MODULES:
    for _local_index, _title in enumerate(_module.titles, start=1):
        _feature_index += 1
        _feature_id = f"{_module.id}-{_local_index:02d}"
        _operation_key = FEATURE_OPERATION_MAP[_feature_id]
        _state = _feature_state(_feature_id, _operation_key)
        _features.append(
            FeatureDefinition(
                id=_feature_id,
                index=_feature_index,
                module=_module.id,
                module_label=_module.label,
                stage=_module.stage,
                title=_title,
                mode=_feature_mode(_module.id, _title),
                risk=_feature_risk(_feature_id, _title, _operation_key),
                operation_key=_operation_key,
                policy=(
                    "blocked"
                    if _state == "blocked"
                    else "mapped"
                    if _operation_key is not None
                    else "unmapped"
                ),
                execution_state=_state,
                reason=_feature_reason(_state),
            )
        )

FEATURE_DEFINITIONS = tuple(_features)
FEATURE_BY_ID = {feature.id: feature for feature in FEATURE_DEFINITIONS}

FEATURE_IDS_BY_OPERATION: dict[str, tuple[str, ...]] = {
    definition.key: tuple(
        feature.id for feature in FEATURE_DEFINITIONS if feature.operation_key == definition.key
    )
    for definition in DEFINITIONS
}
