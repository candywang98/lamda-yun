"""Whitelisted asynchronous operations exposed across product modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cloudctl_domain import Permission


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
    ),
    OperationDefinition(
        "devices.capabilities.refresh",
        "devices",
        "device",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"includeApps"}),
        "Refresh the safe device capability inventory through Edge.",
    ),
    OperationDefinition(
        "groups.membership.reindex",
        "groups",
        "content_group",
        Permission.CONTENT_WRITE,
        True,
        frozenset({"dryRun"}),
        "Rebuild content group membership indexes without modifying frozen snapshots.",
    ),
    OperationDefinition(
        "media.derivative.generate",
        "media",
        "media_asset",
        Permission.CONTENT_WRITE,
        True,
        frozenset({"derivativeProfileId"}),
        "Generate traceable media derivatives while retaining the original object.",
    ),
    OperationDefinition(
        "watermarks.preview.render",
        "watermarks",
        "media_asset",
        Permission.CONTENT_WRITE,
        True,
        frozenset({"ruleVersionId"}),
        "Render a non-destructive watermark preview.",
    ),
    OperationDefinition(
        "works.revision.validate",
        "works",
        "content_revision",
        Permission.CONTENT_WRITE,
        True,
        frozenset({"policyVersion"}),
        "Validate immutable work revisions against content policy.",
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
    ),
    OperationDefinition(
        "xianyu.listing.publish",
        "xy_tasks",
        "device",
        Permission.DEVICE_MAINTAIN,
        False,
        frozenset({"listingBody", "price"}),
        "Dispatch an idlefish text listing form-fill task to the enrolled Companion.",
    ),
    OperationDefinition(
        "task_runs.evidence.export",
        "task_runs",
        "task_run",
        Permission.PUBLISH_READ,
        True,
        frozenset({"format", "redact"}),
        "Export tenant-scoped evidence indexes with mandatory redaction support.",
    ),
    OperationDefinition(
        "automation_packages.qualification.run",
        "automation_packages",
        "automation_package_version",
        Permission.AUTOMATION_MANAGE,
        True,
        frozenset({"matrixProfile"}),
        "Run qualification against an approved compatibility matrix.",
    ),
    OperationDefinition(
        "debug_sessions.evidence.export",
        "debug_sessions",
        "debug_session",
        Permission.DEVICE_MAINTAIN,
        True,
        frozenset({"format"}),
        "Export audited debug-session evidence without exposing device credentials.",
    ),
    OperationDefinition(
        "apk_artifacts.analysis.run",
        "apk_artifacts",
        "apk_artifact",
        Permission.APK_MANAGE,
        True,
        frozenset({"scanners"}),
        "Run malware, permission, signature, and SBOM analysis.",
    ),
    OperationDefinition(
        "apk_rollouts.health_check",
        "apk_rollouts",
        "apk_rollout",
        Permission.APK_MANAGE,
        True,
        frozenset({"observationWindowSeconds"}),
        "Check rollout health without starting installation or bypassing package policy.",
    ),
    OperationDefinition(
        "security_policies.export",
        "security_policies",
        "security_policy",
        Permission.TENANT_ADMIN,
        False,
        frozenset({"format"}),
        "Export the effective tenant security policy without secret material.",
    ),
    OperationDefinition(
        "users_roles.access_review.generate",
        "users_roles",
        "user",
        Permission.TENANT_ADMIN,
        True,
        frozenset({"scope"}),
        "Generate an access review without changing role assignments.",
    ),
    OperationDefinition(
        "audit_exports.generate",
        "audit_exports",
        "audit_event",
        Permission.AUDIT_READ,
        False,
        frozenset({"from", "to", "format"}),
        "Generate a tenant-scoped immutable audit export.",
    ),
)

BY_KEY = {definition.key: definition for definition in DEFINITIONS}

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
        "xy-tasks-01": "xianyu.listing.publish",
        "xy-tasks-02": "publish_plans.snapshot.validate",
        "zz-tasks-01": "publish_plans.snapshot.validate",
        "red-tasks-01": "publish_plans.snapshot.validate",
        "assets-01": "watermarks.preview.render",
        "assets-02": "media.derivative.generate",
    }
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
