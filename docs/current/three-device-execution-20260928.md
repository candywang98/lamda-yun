# 三机交付执行计划（2026-09-28）

## 目标与边界

用户确认按当前连接设备继续，并指定 GPT-5.6 Sol / High 执行推进。
控制器负责排序、设备/部署锁、集成、证据和最终状态；软件子任务使用独立工作树。
本文件是 `tasks.json` 的执行队列补充，不替代其开发/验收状态。

本期设备为一加 9R `b0644fb5`、一加 7 `15faee1d`、华为 VOG-AL10
`APH0219624006517`。ELE-AL00 `GBGDU19830002425` 不计入本次三机目标。
不得因此迁移设备租户、重新绑定账号或删除历史数据。

ADB 只用于开发调试。最终生产路径仍为云端与 Companion，脱离 USB/无线 ADB、
开发电脑和 Edge。真实发送、发布、下架、删除、发货、评价及交易不在本轮授权内。
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
| 2 | 恢复一加、统一验收版本 | 控制器 | WAIT_PREFLIGHT | v4 已构建且与一加 9R 已装 v3 同签名；尚未安装；另两台签名仍待核实，租户/账号/系统权限门禁保留 |
| 3 | 三机订单、通知、商品逐项联调 | 控制器 | WAIT_DEVICE | 每台手机→云端→网页，来源隔离、幂等、无外发；商品持久化缺口单列 |
| 4 | 实机断网与进程恢复 | 控制器 | WAIT_DEVICE | 故障前/中/后同任务证据、无丢失/重传重复；导航不确定时安全暂停；其他设备不被阻塞 |
| 5 | 订单碰撞与历史账号隔离 | Sol High 后续批次 | WAIT_CONTRACT | 明确真实订单号、弱身份策略和可证明归属；历史未知归属不猜测、不删除 |
| 6 | 受控部署与正式交付 | 控制器 | WAIT_INTEGRATION | 代码审查、针对性及集成测试、GitHub 同步、备份/回滚、上线回验、三机最终拔线 |

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
- v4 与一加 9R 已装 APK 的签名相同，已私下保留 v3/v4 APK；未安装、未停应用、
  未清数据、未操作账号/租户。另两台 APK 只读导出超时后终止，签名仍为未知。
- 下一执行门：确认一加 9R 的实机空闲窗口，持精确 serial 锁、复验云端空闲、
  备份/维护模式后原位升级并核对原绑定；无障碍恢复由用户正常授予。
  一加 7 的旧租户处置、华为的平台账号绑定须另行确认，不能自动跨过。

完整命令、哈希及失败记录见
[控制器证据](../../artifacts/three-device-20260928/controller.md)。

## 交付与停止条件

12:24 UTC 新发现的阻塞：一加及华为均因证书指纹不匹配而无法心跳。
控制器已独立核对公网验证链及服务器证书；增加 1D 为设备恢复前置，
冻结契约 `contracts/phase1/cloud-pin-transition-20260928.md`。
不回滚 TLS、不关闭验证、不清队列。设备和云端只读证据见
`artifacts/three-device-20260928/controller.md`。

每个工作包返回基线/分支/提交、修改文件、实际命令/退出码/测试数、
未解决问题及证据路径。控制器审阅后才合并；未经测试不标完成。
任何签名不符、绑定漂移、租户冲突、设备占用或潜在外部提交即停止相应操作，
保留证据和数据，继续其他独立软件任务。

正式应用更新公钥和全仓库 Python/Android CI 的已知问题仍为独立缺口；
不得用测试公钥、跳过安全门或前端 CI 通过掩盖。长期耐久保留后续专项，
但当前服务恢复必须如实验证。没有最终三机拔线证据时，不改为 DEVICE_ACCEPTED。
