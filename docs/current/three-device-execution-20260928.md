# 三机交付执行计划（2026-09-28）

## 目标与边界

用户确认按当前连接设备继续，并指定 GPT-5.6 Sol / High 执行推进。
父线程负责规划、委派和复核；指定 worker 执行获批的仓库修改、构建和测试。
控制器仍负责排序、设备/部署锁、集成、证据和最终状态；软件子任务使用独立工作树。
本文件是 `tasks.json` 的执行队列补充，不替代其开发/验收状态。

本期设备为一加 9R `b0644fb5`、一加 7 `15faee1d`、华为 VOG-AL10
`APH0219624006517`。ELE-AL00 `GBGDU19830002425` 不计入本次三机目标。
不得因此迁移设备租户、重新绑定账号或删除历史数据。

ADB 只可作为经授权的可选开发/诊断工具。生产路径执行期间不得调用 ADB、开发电脑
runner 或 Edge；物理线缆是否连接不是验收门槛，也不能单独证明路径独立。接线证据与
实际生产调用路径验收分开记录。真实发送、发布、下架、删除、发货、评价及交易不在本轮授权内。
不得 `force-stop`、清数据或卸载 Companion。安装/恢复须核对精确设备、绑定、签名、
生产任务占用及本地设备锁；系统权限由正常用户操作授予。

## 已有证据与本轮初始状态

- 网页：`web-qa-e328929262e4` 的线上只读检查 8/8，通过范围见
  [发布记录](../../artifacts/web-qa-20260928/deployment.md)，不是全部业务验收。
- 订单：一加 v3 接线单屏/三屏采集及幂等重放通过，见
  [实测记录](../../artifacts/order-device-20260927/connected-report.md)。
- 恢复软件测试：`OrderDeliveryIntegrationTest` 已有 35 项通过，
  含本会话补充的 3 项重开/补传测试，不替代真实进程终止或断网实验。
- 本轮 ADB 读取：三台均为 `device`；一加 9R v3 的进程及绑定服务未运行，
  系统历史记录 2026-09-27 23:19 终止；华为旧版 0.1.0 运行且无障碍 Bound；
  一加 7 旧版 0.1.0 被禁用且无 Bound。不能从 ADB 可用推断业务就绪。
- 历史记录显示一加 7 与一加 9R 可能属于不同租户。必须重新核对，
  不以凑齐三台为由自动迁移或重新入网。

## 执行队列

| 阶段 | 工作项 | 负责人 | 状态 | 通过标准 |
| --- | --- | --- | --- | --- |
| 0 | 冻结三机范围、保护已有修改、建立基线 | 控制器 | COMPLETE | 基线 `8017114`；计划校验通过，既有恢复测试纳入检查点 |
| 1A | 三机只读前置检查工具 | Sol High A | SOFTWARE_COMPLETE | 已整合 `97d2b6e` / `6db4900`；主仓库 29/29 测试通过；实际三机检查仍返回未就绪 |
| 1B | 旧订单通道覆盖保护 | Sol High B | SOFTWARE_COMPLETE | 已整合 `944c773`；主仓库订单回归 115 passed / 3 SQLite-only skips，PG 并发测试通过；尚未部署 |
| 1C | 手机与云端就绪预检 | 控制器 | IN_PROGRESS | 检查绑定、版本、租户、任务/租约、权限；无外部业务提交 |
| 1D | 已核验的云端证书轮换兼容 | Sol High C | SOFTWARE_COMPLETE | 已整合 `7e2d985`；主线 debug 1294/1294、v4 验收变体 1280/1280；编译代码的生产 TLS/健康读取通过，不代表手机已更新 |
| 1E | 维护模式拒领任务不停止心跳 | Sol High C 后续 | SOFTWARE_COMPLETE | v5 真机窗口 `FAILED/NOT_PROVEN` 保留为历史；八字段 envelope 兼容修复随后封装为 v6，并在一加 9R 单次受控窗口证明维护期延迟领任务后心跳持续及退出维护恢复。该证明仅覆盖一加 9R 维护恢复，不提升其余设备或业务验收状态 |
| 2 | 恢复一加、统一验收版本 | 控制器 | PARTIAL_DEVICE | 一加 9R 当前已原位安装 v6，单次受控窗口已证明维护恢复，原绑定/身份/权限/设置及计数保持；该结果仅限一加 9R，另两台未升级且租户/账号门禁保留，三机统一验收仍未完成 |
| 3 | 三机订单、通知、商品逐项联调 | 控制器 | WAIT_DEVICE | 每台手机→云端→网页，来源隔离、幂等、无外发；商品持久化缺口单列 |
| 4 | 实机断网与进程恢复 | 控制器 | WAIT_DEVICE | 故障前/中/后同任务证据、无丢失/重传重复；导航不确定时安全暂停；其他设备不被阻塞 |
| 5 | 订单碰撞与历史账号隔离 | Sol High 后续批次 | WAIT_CONTRACT | 明确真实订单号、弱身份策略和可证明归属；历史未知归属不猜测、不删除 |
| 6 | 受控部署与正式交付 | 控制器 | WAIT_INTEGRATION | 代码审查、针对性及集成测试、GitHub 同步、备份/回滚、上线回验、三机生产路径未调用 ADB/开发电脑 runner/Edge 的证据 |

## 首批冻结工作包

共同基线为 `80171144e3032cfac80924151a7d76839b9a20b5`。
已实际启动两个 `gpt-5.6-sol` / `high` 子任务，分支为
`agent/sol-preflight-20260928` 与 `agent/sol-order-guard-20260928`。
所有软件工作不得连接生产数据库、操作手机、安装 APK 或自行部署。

### 1A：只读设备预检

- 写域：`scripts/three_device_preflight.py`、
  `tests/ops/test_three_device_preflight.py`、
  `artifacts/three-device-20260928/worker-a.md`。
- 输入：用户显式指定的精确 serial；不得自动选择第一台、通配符或 Wi-Fi 别名。
- 仅读取设备枚举、getprop、包信息、禁用列表、pidof 和无障碍服务。
- 输出 JSON 只保留诊断必需字段；不保存原始日志、界面、账号信息或凭据。
- 任一超时、未授权、无法解析的必要状态按 UNKNOWN/NOT_READY 处理，不猜测就绪。
- 只能声称本地设备前置状态；不能声称云端绑定、账号已登录或三机验收通过。
- 验证：`pytest -q tests/ops/test_three_device_preflight.py`；
  手机实际运行由控制器串行安排。

### 1B：旧订单投影保护

- 冻结契约：
  `contracts/phase1/order-legacy-projection-guard-20260928.md`。
- 写域：`services/control-api/src/cloudctl_api/fleet_orders.py`、
  `tests/integration/test_order_legacy_guard.py`、
  `artifacts/three-device-20260928/worker-b.md`。
- 只修 legacy 覆盖 durable 投影；不改 wire schema、不加数据库迁移、
  不猜测历史归属、不声称已修订单身份碰撞。
- 验证：新回归及已有 orders sync/checkpoint/delivery 测试；
  PostgreSQL 验证只用隔离测试库。

## 2026-09-28 集成结果

- 1A、1B、1D 的软件交付均已整合；没有将任何任务改为 DEVICE_ACCEPTED。
- 主线 v4 的 debug 1294 项和 business-acceptance 1280 项完整单测通过，
  `assembleBusinessAcceptance` 和 vital lint 通过。版本为
  `0.1.0-business-acceptance.4`，构建源码标记 `d200dc2-dirty`。
  `dirty` 包含工作区原有未跟踪材料，不能称为全工作区 clean 构建。
- 控制器使用实际编译的 `PinnedTrustManager`，验证生产叶证书、默认 CA/hostname、
  旧 pin 到已核验新叶的 TLS 握手及无认证 `/health/ready` 读取；负例 3 项通过。
  测试发生在开发电脑，不是手机、WebSocket 或断网恢复实测。
- 后端候选采用已部署 `557f547` 加单个 `fleet_orders.py` 覆盖；核对 202 个运行时
  Python 文件仅该文件不同。候选订单测试 115 passed / 3 SQLite-only skips。
  后端尚未部署，不以主线测试或候选测试代替上线回验。
- 安装前已核对 v4 与一加 9R 原 APK 签名相同，私下保留 v3/v4 APK；随后已按用户
  确认完成原位升级，结果见下节。未显式停应用、清数据或操作账号/租户。
  另两台 APK 只读导出超时后终止，签名仍为未知。
- 一加 7 的旧租户处置、华为的平台账号绑定须另行确认，不能自动跨过。

完整命令、哈希及失败记录见
[控制器证据](../../artifacts/three-device-20260928/controller.md)。

## 2026-09-28 一加升级结果

用户确认空闲窗口后，仅对一加 9R `b0644fb5` 执行原位升级。
14:13:58Z 至 14:14:02Z，v3 升级到 v4 成功；签名、原绑定及凭据、账号绑定、
12 条权限记录、4 项 secure 设置、UID 和首次安装时间均保持。
手机私有数据库不可读，不作逐字节数据库保存声明。

升级自动启动后首次心跳成功，无障碍组件也重新连接，但维护期 claim 409
触发已有 `syncLoop.stopSelf()`，后续心跳停止。服务没有持续运行，不能仅据首次
上线宣称恢复完成。维护模式已于 14:14:09Z 恢复 false/version10，fencing14 已释放。

持 fencing15、复验云端空闲后，于 14:19:40Z 正常启动一次 MainActivity。
设备日志在 14:19:42、14:20:03、14:20:24、14:20:46Z 记录成功心跳；
前台同步服务存在，确切无障碍组件 `hasBound=true`。14:21:45Z 云端再次确认
新鲜活动、原绑定和账号不变、任务379/外发23/订单14/回执6不变，fencing15 已释放。
ADB 接线且使用一次正常启动，不是独立恢复或最终拔线验收。

维护期拒领恢复修复按
`contracts/phase1/claim-maintenance-recovery-20260928.md` 派给 Sol High；
证据见 `artifacts/three-device-20260928/v4-install-summary.json`、
`v4-cloud-after-install.json`、`v4-recovery-summary.json` 和控制器记录。

后续脱敏日志保留 14:19:42.586Z 至 14:29:18.432Z 的 28 次成功心跳。
14:34:54Z 云端复核仍为空闲、原绑定及账号不变、维护 false/version10，
任务379/外发23/订单14/回执6均不变。云端 `last_seen` 同时受其他认证请求影响，
不能用其样本数代替心跳次数；接线观察也不代表锁屏耐久或断网恢复。

## 2026-09-28 维护恢复修复集成

- GPT-5.6 Sol / High 提交 `713af64` 已审查并整合为 `19da0d8`。
  仅在 claim 请求边界识别精确维护 409，按原有退避延迟下一轮；
  不入队、不执行本地任务、不停止同步服务，其他 HTTP 错误保留原行为。
- 控制器在同一主线代码上完成两个变体完整回归：debug 175 suites / 1303 tests，
  businessAcceptance 175 suites / 1289 tests；均为 0 failures/errors/skips，
  各包含 9 项维护拒领测试。Gradle exit 0，完整结果见
  [机器可读测试证据](../../artifacts/three-device-20260928/maintenance-mainline-tests.json)。
- 测试执行生产实际调用的 claim-pass 函数及回调，不是完整 Android Service
  生命周期测试，不能据此声称已实测后台心跳持续运行。
- 本修复已构建为 versionCode 5 / `0.1.0-business-acceptance.5` 候选，源码标记
  `a3eb419`，APK SHA256 为 `8b40b9284be9f6f7aca812792ff9315d9376803b9c6ec3d1ad9190241e0e5b0f`；
  已于受控窗口原位安装到一加，原绑定、账号、权限、设置及计数保持，v3/v4 私有制品
  均保留。维护期仅记录 1 次确切目标心跳、0 次 deferral，随后同步服务消失；退出维护
  后 150 秒仍无服务或心跳，因此 `maintenanceRecovery` 与
  `postMaintenancePresence` 均为 `NOT_PROVEN`。
- 只读诊断确认部署端 `ConflictError` 返回八字段 problem envelope，而 `a3eb419`
  classifier 仅接受单字段 body；真实响应因此进入不可重试 409 的 `stopSelf()` 路径。
  协议不匹配已确认；具体 server journal 行仍无目标归属，不作为目标请求直接证明。
- maintenance 已恢复 `false/version12`，fencing16 已以 `FREE/released_fencing=16`
  释放。原私有摘要的 `lockReleased=false` 是状态字判定错误，原证据保留；不存在锁泄漏。
- 仅限 claim 端点、外层 409、精确 detail 且完整 envelope 的 status/code/type 一致
  兼容修复在 v5 窗口结束时仅完成软件回归，尚未组装或真机复验；这是当时状态，原始
  `FAILED/NOT_PROVEN` 证据保持不变。该修复后来封装为 v6 并完成下一节所述单次受控验收。

## 一加 9R v6 维护恢复结果

- 当前主线 `2b6538c` 已包含脱敏结果
  `artifacts/three-device-20260928/v6-device-result.json`。候选为 clean source
  `9c98c5f`、versionCode 6 / `0.1.0-business-acceptance.6`；完整 debug
  1307/1307、businessAcceptance 1293/1293、assembly/vital lint 及聚焦 harness/锁测试
  99 项均通过。
- 控制器授权的唯一窗口为 `2026-09-28T17:52:31Z` 至 `17:54:38Z`，只对一加 9R
  `b0644fb5` 执行一次原位安装；安装 attempts=1，未手动启动，也未导航、
  `force-stop`、卸载、清数据、重启或改变网络。自动启动进程由 v5 PID `21512`
  变为 v6 PID `1691`。
- `maintenance=true/version13` 期间，PID 过滤日志记录 3 次成功心跳和 6 次维护延迟领任务；
  5/5 运行样本均有前台同步服务和 user-0 无障碍精确绑定。恢复
  `maintenance=false/version14` 后，同一 PID 再记录 3 次成功心跳，6/6 运行样本健康。
  server journal 仍无目标归属，目标证明来自手机 PID 过滤日志，不将未归属日志冒充证据。
- 活动绑定、租户、账号身份和绑定计数 `1/1/1` 保持；App ID、UID、首次安装时间、
  12 条权限记录、4 项 secure 设置及任务379/外发23/订单14/回执6均保持。
  最终全局/目标占用为空、receive-only notification 模式保持，锁为 `FREE`，
  fencing17 已释放并独立回读确认。
- 结果为一加 9R 的 `maintenanceRecovery=PROVEN` 与
  `postMaintenancePresence=PROVEN`，只证明该机该维护恢复窗口。它不证明一加 7、
  华为 VOG、三机业务交付、长期保活、断网补传、进程故障恢复、订单碰撞/历史账号隔离，
  也不证明业务生产路径未调用 ADB、开发电脑 runner 或 Edge。按 D-15，物理拔线本身不是
  验收门槛，仍须按实际调用路径补齐后续证据。

## 交付与停止条件

12:24 UTC 发现一加及华为均因证书指纹不匹配而无法心跳。
控制器已独立核对公网验证链及服务器证书；增加 1D 为设备恢复前置，
冻结契约 `contracts/phase1/cloud-pin-transition-20260928.md`。
一加升级 v4 后已恢复成功心跳；华为尚未升级，不能沿用一加结果宣称已恢复。
不回滚 TLS、不关闭验证、不清队列。设备和云端只读证据见
`artifacts/three-device-20260928/controller.md`。

每个工作包返回基线/分支/提交、修改文件、实际命令/退出码/测试数、
未解决问题及证据路径。控制器审阅后才合并；未经测试不标完成。
任何签名不符、绑定漂移、租户冲突、设备占用或潜在外部提交即停止相应操作，
保留证据和数据，继续其他独立软件任务。

正式应用更新公钥和全仓库 Python/Android CI 的已知问题仍为独立缺口；
不得用测试公钥、跳过安全门或前端 CI 通过掩盖。长期耐久保留后续专项，
但当前服务恢复必须如实验证。没有三机真实生产调用路径及其未调用 ADB、开发电脑
runner 或 Edge 的证据时，不改为 DEVICE_ACCEPTED；线缆连接状态本身不构成通过或失败。
