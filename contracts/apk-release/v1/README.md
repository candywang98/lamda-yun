# apk-release/v1 — APK 更新策略与制品发布（U10）

- 契约版本：`apk-release/v1@20260917.1`，**FROZEN**（创建即冻结；实现不得反向改写本契约，只能新增独立版本目录）。
- 结构化定义：[apk-release-v1.schema.json](./apk-release-v1.schema.json)
- 与 P14 Recipe 生命周期（`recipes/active`、任务级 recipe pin）**是两条独立轨道**：Recipe 管"设备上跑哪套自动化逻辑"，apk-release 管"设备上装哪个 APK 制品"。两者复用同一套审计 / Ed25519 签名验签设施，但状态机、表、端点互不重叠。

## 1. 资源模型

### 1.1 制品（既有 `apk_artifact`，准入在先）

APK 制品必须先经 `/api/v1/apk-artifacts` 注册：分析报告 Ed25519 验签 + 准入策略（denied permissions / ABI / severity / debuggable / cleartext / targetSdk 基线）全部通过后才是 `CLEAN` 制品。apk-release/v1 不重复验签，只引用已准入制品；未准入制品发布 → `422 APK_ARTIFACT_NOT_ADMITTED`。

### 1.2 发布（`apk_release`）

一条发布记录 = 一个已准入制品 + 灰度环 + 升级门槛，字段：

| 字段 | 语义 |
|---|---|
| `packageName` / `versionCode` / `versionName` | 来自已准入制品，不可改写 |
| `signatureDigest` | APK 签名证书摘要（SHA-256） |
| `sha256` | APK 文件 SHA-256，设备侧下载后校验的基准 |
| `ring` | `canary` \| `early` \| `all`，当前灰度环 |
| `minCapability` | 最低设备能力要求，闭集 `{sdkInt, abis}`；空对象 = 无额外要求 |
| `dataSchema` | `{minCompatible, current}` 数据 schema 兼容窗口，`current >= minCompatible >= 1` |
| `requiresUserConfirmation` | 见 §4 |
| `status` | `ACTIVE` → `RETIRED`（单向） |

**不可覆盖**：`(tenant, artifactId)` 唯一。同一制品 id 再次发布 → `409 APK_RELEASE_EXISTS`，任何字段都不允许原地改写；要改门槛就发新制品新发布。

### 1.3 安装候选（`apk_release_target`，设备侧 pin）

`(tenant, deviceId, releaseId)` 唯一；同一设备同一包同时最多一条 `OFFERED` 候选（部分唯一索引）。状态 `OFFERED → DOWNLOADED → INSTALLED`（单向）。

**撤销不破坏 pin**：`:retire` 只把发布置 `RETIRED`，不触碰任何 target；已被 pin 的候选仍可被设备拉取、校验哈希、下载完成（`releaseStatus` 会如实显示 `RETIRED`，由设备侧决定提示策略）。retire 后的新增 assign → `409 APK_RELEASE_RETIRED`。

## 2. 端点

| 方法 & 路径 | 权限 | 语义 |
|---|---|---|
| `POST /api/v1/apk-releases` | `apk.manage` | 发布记录（201 / 409 APK_RELEASE_EXISTS） |
| `GET /api/v1/apk-releases` | `apk.manage` | 租户内列表 |
| `GET /api/v1/apk-releases/{id}` | `apk.manage` | 单条；跨租户 404 |
| `POST /api/v1/apk-releases/{id}:retire` | `apk.manage` | 撤销（body: `reason`）；重复 retire → 409 |
| `POST /api/v1/apk-releases/{id}:assign` | `apk.manage` | 为设备创建安装候选（body: `targetDeviceIds`），逐设备过 §3 门禁；幂等（重复 assign 返回既有 target） |
| `GET /companion/v2/apk/candidates` | Companion bearer | 本设备的 `OFFERED`/`DOWNLOADED` 候选（含安装描述符） |
| `POST /companion/v2/apk/candidates/{candidateId}:report-downloaded` | Companion bearer | 上报下载文件 SHA-256；不匹配 → `422 APK_DOWNLOAD_HASH_MISMATCH` 且候选保持 `OFFERED` |

审计事件：`apk.release.published` / `apk.release.retired` / `apk.release.assigned` / `apk.release.downloaded`。

## 3. 下发门禁（assign 时逐设备判定，任一不过即整单 4xx 拒绝）

1. **租户隔离**：release / device 查询全部 tenant-scoped，跨租户读或发 → `404 NOT_FOUND`。
2. **环匹配**：设备环来自 `device.labels` 中的 `ring:<name>` 标签；无标签设备只吃 `all` 环。`ring=all` 的发布可发任意设备，其余环要求设备标签精确匹配，否则 `422 APK_RING_MISMATCH`。
3. **能力路由**：`minCapability.sdkInt` 对比 `device.capabilities.sdkInt`，`minCapability.abis` 要求设备上报的 `capabilities.abis` 为其超集；设备未上报或不足 → `422 APK_CAPABILITY_INSUFFICIENT`（能力不足不下发）。
4. **禁止 versionCode 降级**：设备已装版本取 `device.target_app_versions[packageName]`（十进制 versionCode 字符串）。已装 >= 候选 versionCode → `422 APK_VERSION_DOWNGRADE`。不同设备各自保留各自旧版，互不强制拉平。
5. **数据 schema 兼容**：设备上报 `device.capabilities.dataSchemaVersions[packageName]`（整数）。上报值 < `dataSchema.minCompatible` → `422 APK_SCHEMA_INCOMPATIBLE`；未上报视为不可判定，放行（门禁只拒绝可证明的不兼容）。
6. **任务抢占保护**：设备存在 `mobile_task.status IN (CLAIMED, RUNNING)` 或 `business_state IN (PAUSED_WAITING_USER, RECONCILING)` 的任务 → `409 APK_DEVICE_BUSY`。CLAIMED 是 RUNNING 的租约前置态，一并保护，防止 preflight 期间被抢占。
7. **单候选约束**：同设备同包已有一条其他发布的 `OFFERED` 候选 → `409 APK_CANDIDATE_EXISTS`。

## 4. `requiresUserConfirmation` 字段语义（重要）

- `true`：设备**必须**先取得用户确认才可安装（默认值）。
- `false`：仅表示操作方声明"无需确认"；**绝不构成静默安装保证**。设备侧本地策略、系统安装器 UI、ROM 限制随时可以否决，SDK 标志（如 PackageManager 的静默安装 flag）不覆盖本字段。
- 该值在 assign 时快照进 target 行，设备拉取的候选里带的是快照值；发布后续改动（若发新发布）不影响已 pin 候选。

## 5. 错误码

全部走共享 problem+json envelope（`urn:cloudctl:problem:<code.lower()>`）。专用码：

`APK_RELEASE_EXISTS` / `APK_RELEASE_RETIRED` / `APK_CANDIDATE_EXISTS` / `APK_CANDIDATE_STATE` / `APK_DEVICE_BUSY`（均 409）；`APK_RING_MISMATCH` / `APK_CAPABILITY_INSUFFICIENT` / `APK_VERSION_DOWNGRADE` / `APK_SCHEMA_INCOMPATIBLE` / `APK_DOWNLOAD_HASH_MISMATCH` / `APK_ARTIFACT_NOT_ADMITTED`（均 422）；租户越权复用 `NOT_FOUND`（404）。

## 6. 存储

迁移 `20260917_0025_add_apk_release_rollout`：新表 `apk_release`、`apk_release_target`（含部分唯一索引 `uq_apk_release_target_offered`），downgrade 直接删表——发布/候选记录可由上游准入台账 + 审计事件重建推导。
