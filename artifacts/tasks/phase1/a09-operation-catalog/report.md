# A09 交付证据：operation 目录逐动作登记（31 个 xy-tasks 操作）

- TaskID: A09-WG
- Baseline: 29f19dd（分支 agent/a09-operation-catalog）
- 契约依据: contracts/parallel/K03/task-schedule-v1.md §2（operationId 身份链）、contracts/parallel/K05/platform-recipe-v1.md §2/§4（CommandType 封闭枚举、open-only 语义）、docs/phase1/field-map.json（31 操作清单）
- 变更文件: services/control-api/src/cloudctl_api/{operation_catalog.py, operation_parameters.py, command_factory.py}；tests/unit/test_operation_catalog.py（新增）；tests/integration/{test_backend_operations.py, test_operation_parameter_contracts.py}（消费方同步，见下）

## 1. 31 操作登记表

key 规则：field-map 有 commandType 的复用为目录 key（xy-tasks-01 保留既有 xianyu.listing.publish 铸造键）；无 commandType 的共享服务/教程页登记 xianyu.shared.* / xianyu.guide.* 清单键。状态三档：可执行（今天可铸生产命令）/ contract_only（登记但无生产 CommandV1 类型，铸造 fail-closed）/ pending真机（AVAILABILITY_PENDING，T102 前置）。

| 操作ID | 标题 | 目录 key | 状态 | result 类型 | 参数模型 | 权限 | 风险 |
|---|---|---|---|---|---|---|---|
| xy-tasks-01 | 发布商品 | xianyu.listing.publish | 可执行 | XianyuPublishListingResult | XianyuListingPublishParameters | device.maintain | standard |
| xy-tasks-02 | 发布帖子 | xianyu.publish_post | pending真机 | XianyuPublishPostResult | XianyuPublishPostParameters | device.maintain | approval |
| xy-tasks-03 | 擦亮商品 | xianyu.polish_goods | contract_only | XianyuPolishGoodsResult | XianyuPolishGoodsParameters | device.maintain | approval |
| xy-tasks-04 | 上架商品 | xianyu.shelf_up | contract_only | XianyuShelfUpResult | XianyuShelfUpParameters | device.maintain | approval |
| xy-tasks-05 | 下架商品 | xianyu.shelf_down | contract_only | XianyuShelfDownResult | XianyuShelfDownParameters | device.maintain | approval |
| xy-tasks-06 | 删除商品 | xianyu.delete_goods | contract_only | XianyuGoodsDeletedResult | XianyuDeleteGoodsParameters | device.maintain | approval |
| xy-tasks-07 | 删除帖子 | xianyu.delete_post | pending真机 | XianyuPostDeletedResult | XianyuDeletePostParameters | device.maintain | approval |
| xy-tasks-08 | 绑定闲鱼 | xianyu.bind_account | contract_only | XianyuAccountBoundResult | XianyuBindAccountParameters | device.maintain | approval |
| xy-tasks-09 | 签到鱼币 | xianyu.checkin_coins | contract_only | XianyuCoinCheckinResult | XianyuCoinCheckinParameters | device.maintain | approval |
| xy-tasks-10 | 鱼币抵扣 | xianyu.coin_discount | contract_only | XianyuCoinDiscountAppliedResult | XianyuCoinDiscountParameters | device.maintain | approval |
| xy-tasks-11 | 鱼币推广 | xianyu.coin_promote | contract_only | XianyuCoinPromoteStartedResult | XianyuCoinPromoteParameters | device.maintain | approval |
| xy-tasks-12 | 一键小刀 | xianyu.bargain | contract_only | XianyuBargainOfferedResult | XianyuBargainParameters | device.maintain | approval |
| xy-tasks-13 | 一键降价 | xianyu.price_cut | contract_only | XianyuPriceUpdatedResult | XianyuPriceCutParameters | device.maintain | approval |
| xy-tasks-14 | 一键好评 | xianyu.review | contract_only | XianyuReviewPostedResult | XianyuReviewParameters | device.maintain | approval |
| xy-tasks-15 | 重启闲鱼 | xianyu.restart_app | contract_only | XianyuAppRestartedResult | XianyuRestartAppParameters | device.maintain | approval |
| xy-tasks-16 | 删除动态 | xianyu.delete_feed | contract_only | XianyuFeedDeletedResult | XianyuDeleteFeedParameters | device.maintain | approval |
| xy-tasks-17 | 删除消息 | xianyu.delete_message | contract_only | XianyuMessageDeletedResult | XianyuDeleteMessageParameters | device.maintain | approval |
| xy-tasks-18 | 删除留言 | xianyu.delete_comment | contract_only | XianyuCommentDeletedResult | XianyuDeleteCommentParameters | device.maintain | approval |
| xy-tasks-19 | 草稿上架 | xianyu.draft_publish | contract_only | XianyuDraftRelistedResult | XianyuDraftPublishParameters | device.maintain | approval |
| xy-tasks-20 | 编辑重发 | xianyu.reedit | contract_only | XianyuReeditRelistedResult | XianyuReeditParameters | device.maintain | approval |
| xy-tasks-21 | 托管无忧卖 | xianyu.wuyoumai | contract_only | XianyuWuyoumaiEnabledResult | XianyuWuyoumaiParameters | device.maintain | approval |
| xy-tasks-22 | 快速编辑重发 | xianyu.fast_reedit | contract_only | XianyuFastReeditRelistedResult | XianyuFastReeditParameters | device.maintain | approval |
| xy-tasks-23 | 快速下架商品 | xianyu.fast_shelf_down | contract_only | XianyuFastShelfDownResult | XianyuFastShelfDownParameters | device.maintain | approval |
| xy-tasks-24 | 采集宝贝信息 | xianyu.collect_listings | contract_only | XianyuListingsCollectedResult | XianyuCollectListingsParameters | device.maintain | standard |
| xy-tasks-25 | 通用地址池 | xianyu.shared.generic_address_pool | contract_only | GenericAddressPoolUpdatedResult | GenericAddressPoolParameters | content.write | standard |
| xy-tasks-26 | 设备地址池 | xianyu.shared.device_address_pool | contract_only | DeviceAddressPoolUpdatedResult | DeviceAddressPoolParameters | content.write | standard |
| xy-tasks-27 | 描述池 | xianyu.shared.description_pool | contract_only | DescriptionPoolUpdatedResult | DescriptionPoolParameters | content.write | standard |
| xy-tasks-28 | 标签池 | xianyu.shared.tag_pool | contract_only | TagPoolUpdatedResult | TagPoolParameters | content.write | standard |
| xy-tasks-29 | 图片水印 | xianyu.shared.watermark | contract_only | XianyuWatermarkRenderedResult | XianyuWatermarkParameters | content.write | standard |
| xy-tasks-30 | 违禁词检测 | content.forbidden_words.scan | contract_only | ForbiddenWordsScanResult | ForbiddenWordsScanParameters | content.write | standard |
| xy-tasks-31 | 视频操作教程 | xianyu.guide.videos | contract_only | VideoGuideContentResult | VideoGuideParameters | content.read | standard |

- 46 个 OperationDefinition 的 result_type 两两不同（含既有 15 个，各自补齐）；删除族（06/07/16/17/18）各自携带资源语义且互不相同；擦亮=Polish、降价=PriceUpdated、好评=ReviewPosted、推广=PromoteStarted——没有动作被统一映射成 delete 或成功（红线，测试 `test_result_types_are_pairwise_distinct_and_non_generic` / `test_result_types_match_action_semantics` 断言）。
- xy-tasks-09/10/11/14（签到鱼币/鱼币抵扣/鱼币推广/一键好评）保持 BLOCKED_FEATURE_IDS 生产策略封禁，登记 prerequisite 明示策略前置；feature 层 policy=blocked 不变。
- xy-tasks-02/07 AVAILABILITY_PENDING → pending_device_verification，prerequisite 载明 T102 真机核查；feature 层 execution_state=contract_only，不静默剔除。
- FEATURE_OPERATION_MAP / PAGE_OPERATION_KEYS：31 个 xy-tasks feature 全部映射到各自登记 key（xy-tasks-02 由 publish_plans.snapshot.validate 占位改为自身 pending 登记）。

## 2. 参数允许列表（Strict 模型）

- 30 个新 key + 扩展的 xianyu.listing.publish 全部进 CORE_MODELS；`allowed_parameters` 与模型字段逐一相等（测试 `test_core_parameter_models_cover_all_xy_registrations`）。
- 全部 extra="forbid"：任意未知参数 422（测试 `test_all_xy_operations_reject_unknown_parameters`）。
- 预算/目标红线：promotePackage/promoteItem、dikouType/dikouTarget、delete target、reviewTarget、price_cut target 全部为封闭 Literal；percentCut 1..50 且与 amountCut 恰选其一（测试 `test_budget_and_target_drift_is_rejected`）。漂移示例：coins_9999、every_listing、percentCut=99、target=whatever 均拒绝。
- pending（02/07）与无参数动作（15/19/23/24/31、四个池）为空契约——空即 fail-closed，任何参数都拒绝。
- 31 个 feature 的 pageParameters 页模型齐备（PAGE_MODELS 与 PAGE_OPERATION_KEYS 键集相等，模块加载时校验）。

## 3. mint 链路（command_factory）

- PRODUCTION_ALIASES 未扩：唯一可铸的 xy 操作仍是 xy-tasks-01 → xianyu.publish_listing.v1（open-only，K05 冻结枚举，未新增 CommandType，双端零同步需求）。
- 其余 30 个：mapped 未接线 → `catalogued (contract_only) but not enabled`；AVAILABILITY_PENDING → 报 T102 原因。新增 `xy_catalog_registration()` 供审计反查（key/resultType/availability/prerequisite）。
- 铸造输出新增 resultType 字段（xy-tasks-01 = RESULT_TYPES 对齐的 XianyuPublishListingResult），仅作结果身份声明，不改变既有 stamping 通道。

## 4. 测试

- 新增 tests/unit/test_operation_catalog.py：15 个测试（31 全覆盖、key/feature 映射、result 语义、状态分类、允许列表、预算/目标漂移、mint fail-closed、operationId 全链 create→GET 可见 + contract_only 拒绝、field-map 双副本同步）。
- 同步的 2 个消费方测试（越 OwnedPaths 的最小改动，见未决项）：
  - test_backend_operations.py：/operations/catalog 数量 16→46（31 个登记进入目录的直接后果）；
  - test_operation_parameter_contracts.py：移除 xy-tasks-02→publish_plans.snapshot.validate 占位参数化用例（映射已改为自身 pending 登记，zz/red 用例继续覆盖该页契约）。
- 结果（uv run --extra dev pytest -q）：
  - 聚焦：tests/unit/test_operation_catalog.py → 15 passed
  - 全量：716 passed, 1 skipped（基线 702 passed, 1 skipped；+15 新测试、-1 个占位参数化用例，无新失败）

## 5. 未决项 / 移交

1. 越界同步（2 个集成测试文件）已按最小 diff 处理并在此声明，请总控复核归属。
2. Web 端 apps/web/src/data/operations-catalog.ts 的 backendOperationMappings['xy-tasks-02'] 仍指向 publish_plans.snapshot.validate（静态映射向后兼容、不会报错）；建议 W-A 线在 T102 落地后同步为 xianyu.publish_post。
3. contract_only 动作的生产化路径：需先裁决新增 CommandV1 类型（K05 五处同步），本任务未触碰冻结枚举。
4. operation_runtime.py 未改动：BUILTIN_OPERATION_KEYS（operations-lane 执行器）与 A09 登记正交，无需变化。
