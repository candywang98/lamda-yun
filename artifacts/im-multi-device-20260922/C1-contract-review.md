# C1 契约审查：pa-im-m3/20260922.1

日期：2026-09-22（Asia/Shanghai）

结论：本检查点只冻结契约。不是软件通过，不是真机验收。未改 xlsx，未改生产配置，未连接或操作手机。未运行测试、构建或 ADB。

增量契约：`cloudctl-source/contracts/phase1/pa-im-multi-device-inbound-v1.md`

## 实际读取的路径

父契约与采集/上报/展示实现：

- `cloudctl-source/contracts/phase1/pa-im-aggregation-v1.md`（全文，44 行）
- `cloudctl-source/mobile/companion/app/src/main/java/com/company/cloudctl/companion/im/ImMonitor.kt`（全文）
- `cloudctl-source/mobile/companion/app/src/main/java/com/company/cloudctl/companion/im/DutyController.kt`（全文，269 行；本轮复核补读，不再作为未读文件）
- `cloudctl-source/mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/CloudCtlAccessibilityService.kt` 第 168–242 行（通知入站）
- `cloudctl-source/mobile/companion/app/src/main/java/com/company/cloudctl/companion/service/CompanionSyncService.kt` 第 517–582 行（IM 上送）
- `cloudctl-source/services/control-api/src/cloudctl_api/im_routes.py`（全文）
- `cloudctl-source/services/control-api/src/cloudctl_api/im_service.py` 第 1–279 行（ingest 与列表）
- `cloudctl-source/services/control-api/src/cloudctl_api/db.py` 第 878–931 行（IM 表）
- `cloudctl-source/services/control-api/migrations/versions/20260913_0017_im_aggregation.py`（全文）
- `cloudctl-source/services/control-api/migrations/versions/20260915_0020_im_message_delivery_state.py` 第 1–39 行
- `cloudctl-source/apps/web/src/api/im.ts` 第 1–234 行
- `cloudctl-source/apps/web/src/views/ImInboxView.vue` 第 1–329 行（脚本与列表头）

设备与输入通道旁证（只引用已写明的事实，本检查点没有重跑 ADB）：

- `cloudctl-source/artifacts/input-transport-20260922/device-acceptance/production-gate.md` 第 1–19 行
- `cloudctl-source/docs/current/input-transport-20260922.md` 第 29–31 行
- `cloudctl-source/artifacts/input-transport-20260922/semantic-acceptance-checklist.md` 第 1–22 行
- 工作区 `项目交接说明.md` 第 130–136 行（旧说法，已被本轮主会话 ADB 证据否定）
- 工作区 `artifacts/ocr-device-gates-20260922/device-identities.json` 第 1–76 行（2026-09-22 15:50；OnePlus 有 binding，两台华为当时 absent）
- `cloudctl-source/docs/delivery/functional-delivery-progress-2026-09-01.md` 第 69–73 行（旧说法）
- `cloudctl-source/Makefile` 第 16–24 行；`cloudctl-source/apps/web/package.json` 第 6–14 行；`cloudctl-source/scripts/plan_guard.py` 第 79–94 行
- `cloudctl-source/docs/v1/device-matrix.json` 第 4–16 行（历史 serial 被写成 device_id，不采用）
- 工作区 `多智能体开发配套/任务清单_多智能体版.json`：B14 约第 1572–1590 行；P13 验收口径约第 1733–1742 行

`DutyController.kt` 已全文阅读，值班点击差额写在下面，不再回避。仍未读、因此不对测试是否覆盖下结论的文件：`ImMonitorTest.kt`、`DutyWriteArbitration.kt` 全文。任务用的 `event_outbox`（`AutomationStore.kt`）当前 IM 上送路径没有写入，不把它算作 IM 持久 outbox。

## 当前实现与契约的已知差额

### platform 未透传

- 设备模型有 `platform`，去重原材料也含 platform：`ImMonitor.kt` 第 12–25 行，`dedupeKey` 为 `deviceId|platform|peerKey|bucket|text`。
- 无障碍入站按包名写入 `ImEvent.platform`：`CloudCtlAccessibilityService.kt` 第 206、230–238 行。
- 实际上送丢掉 platform，只传 `peerKey`、`peerName`、`text`、`occurredAt`：`CompanionSyncService.kt` 第 566–573 行。
- 入站 schema 没有 platform 字段：`im_routes.py` 第 34–40 行。
- 服务端新线程固定 `platform=PLATFORM`，常量是 `"xianyu"`：`im_service.py` 第 21、222 行。
- 服务端幂等不含 platform：`im_service.py` 第 65–68 行，`device_id|peer_key|bucket|text`。
- 线程唯一约束不含 platform：迁移 `20260913_0017_im_aggregation.py` 第 26 行 `uq_im_thread_peer (tenant_id, device_id, peer_key)`；ORM 同名约束在 `db.py` 第 891 行。

差额：同设备同昵称的不同平台会落进同一线程；重放时设备键与服务端键不一致。契约要求载荷带 platform、线程键与幂等键都含 platform，并用新唯一约束 `uq_im_thread_platform_peer`。迁移不得改写历史 `dedupe_key`，冲突行必须中止而不是合并。唯一约束事实未变：`20260913_0017` 第 26 行与 `db.py` 第 891 行的 `uq_im_thread_peer` 不含 platform；`dedupe_key` 全局 UNIQUE 且现算法不含 platform（`im_service.py` 第 65–68 行）。

### 截断与幂等键不一致

三处长度和键材料不是同一份文本，超长正文重投会被云端当成新消息。短文本重投通过不能代替这一条。

- 设备键用事件全文，不加 `TRUNCATED ` 前缀：`ImMonitor.kt` 第 20–24 行，`"$deviceId|$platform|$peerKey|$bucket|$text"`。
- 通知入站在入键前只做 `text.take(4000)`：`CloudCtlAccessibilityService.kt` 第 235 行。这是前 4000 个 UTF-16 码元，不是 2000 个码点。
- 路由允许正文到 4000：`im_routes.py` 第 38 行。服务端 `MAX_TEXT = 2_000`（`im_service.py` 第 23 行）；`len(text) > 2000` 时先切到 2000，再拼 `"TRUNCATED "`，然后才算键（第 192–201 行）。`len` 按 Unicode 码点。已经带前缀的正文再提交会再加一次前缀。

契约第 4.1 节把设备与服务端收成同一 canonical 文本后再算键，并要求 C4 跨端夹具与 C6 超长正文重投。本审查不把现有短文本幂等测试写成已覆盖超长正文。

### 值班模式会启动闲鱼并点击

上一稿写「未读 DutyController 全文，不在差额里下结论」是错的。本轮已读全文。现有 `DUTY` 不是只读消息页：

- 类注释写明停在闲鱼消息列表、打开未读会话、读气泡再返回：`DutyController.kt` 第 19–24 行。
- `tick` 在 `dutyMayWrite` 时 `runCycle`：第 63–68 行。
- `ensureOnMessageList` 调用 `launchTargetApp(XIANYU_PACKAGE)`，随后 `DutyMessageListNav` 点消息 tab；闲鱼在前台时坐标兜底 `tapRemoteGestureLike`：第 90–117 行。
- `openConversation` 取会话入口屏幕中心并 `tapRemoteGestureLike`：第 189–191 行。
- `backToList` 调用 `dutyBack`：第 232–237 行。

默认配置常量是 `MODE_NOTIFICATION`（`ImMonitor.kt` 第 32 行），但只要云端把该设备配成 `DUTY` 且仲裁允许写，上述点击就会发生。契约改为：本轮只启用 `NOTIFICATION`；不得把这条旧路径写成只读无动作；不在本版本里把值班改成只读实现。单独验收 `DUTY` 必须另写契约。

### IM 队列仍在内存

- `ImMonitor` 的待发集合是 `ArrayDeque`，上限 200：`ImMonitor.kt` 第 89、116、139–141 行。
- 满了就 `pending.removeFirst()`，最旧事件被丢掉，没有溢出日志：同文件第 139–140 行。
- `drain` 先从内存移除，失败再 `requeue`：`CompanionSyncService.kt` 第 561–580 行；`ImMonitor.kt` 第 145–155 行。进程在 drain 之后、确认之前死亡，这批事件不在内存里，也没有本路径的本地持久记录。
- 父契约写「推送通道复用 event_outbox」（`pa-im-aggregation-v1.md` 第 21 行）。当前 `deliverImEvents` 直接 `client.sendImMessages`，没有看到写入 `event_outbox`。任务用的 `event_outbox` 在 `AutomationStore.kt`，不是这条 IM 路径。

差额：契约要求本地持久 outbox、成功才确认、失败退避、重启恢复、溢出可观察且不得丢弃已持久化项。内存 LRU（512）仍可做短时去重，但不能当可靠性边界。

### 列表无 lastMessageText

- 线程视图只有时间、方向、未读，没有正文：`im_service.py` 第 71–81 行。
- Web 类型把 `lastMessageText` 标成后端当前不返回：`im.ts` 第 13–18、72–77 行。未返回时 `summaryPending=true`。
- 列表摘要只在打开线程后用本地消息回填：`ImInboxView.vue` 第 77–88 行。未打开的会话没有最近正文。

差额：契约要求列表直接显示服务端 `lastMessageText`。

### 前端无短轮询

- 会话只在 `onMounted`、手动「刷新」、过滤变更时拉取：`ImInboxView.vue` 第 49–60、220–225、261–264、277–286 行。
- 在该文件检索 `visibilitychange`、`setInterval`、`poll`：无匹配。因此没有短轮询，也没有「轮询失败」这条路径。
- 已有能力：全部设备（`deviceFilter` 为空不过滤，第 37–40 行）、设备下拉（第 275–280 行）、未读计数与「只看未读」（第 69–72、282–284 行）。
- `refreshThreads` 的 `selected`：只有请求成功且 `preserveSelection` 为假或选中 id 不在新列表中，才把 `selected` 置空并清空消息（第 52–54 行）。`catch` 只写 `errorMessage`，不改 `selected`（第 56–58 行）。这不是轮询失败保持；当前没有轮询。上一稿写「一次失败会保留旧 selected」容易被读成该行为已经实现了契约第 6 节的失败保持，已删除这句。

差额：契约要求可见时约 5 秒短轮询、隐藏时停止、刷新后按 thread id 保持选中，并且新轮询失败时不清空列表、不重置选中。后一句是对尚未存在的轮询的要求。不新要求 WebSocket。

### 其他冻结项（不是本轮实现，只避免误报）

- 回复 API 与按钮仍在：`im_routes.py` 第 98–100 行，`ImInboxView.vue` 第 90–107 行。本轮禁止调用，只回归保护。
- 设备身份已按主会话本轮 ADB 证据改正，不再沿用旧交接稿。三台是：`b0644fb5` 与 `192.168.5.6:5555` 同为 OnePlus `LE2100`；`APH0219624006517` 是 `HUAWEI VOG-AL10`，不是疑似 OnePlus；`GBGDU19830002425` 是 `HUAWEI ELE-AL00`。`项目交接说明.md` 第 135 行和 `functional-delivery-progress-2026-09-01.md` 第 72 行的「疑似 OnePlus」作废。
- 本检查点没有重跑 `adb`。15:50 的 `device-identities.json` 只证明当时 OnePlus 在线且 binding 为 `4aabc387-6e4b-4b59-a525-b1c119ec7f5b`（第 47–50 行），两台华为当时 `absent`（第 66–75 行）。那次缺席不否定主会话现在的机型读数，也没有这两台的 `device_id`。C5 必须当场再读 binding，禁止用 serial 填生产身份。
- 主会话给出的安装事实写进 C5：VOG 与 OnePlus 当前 Companion 0.1.0，ELE 当前未安装。同签名才覆盖升级；签名不一致不得卸载或清数据；ELE 可首次安装。无障碍和华为后台常驻只能用户手工开启，禁止静默改 secure settings。C5 可以做这些接入动作，仍然不得发消息。
- 上一稿把 C4 写成「只跑直接对应测试」、把 C5 写成「本检查点不安装」，都与批准计划不符，已改。C4 现列聚焦 IM、全量 JVM、lint、debug APK、两份后端集成测试、ruff/pyright/mypy、`im-inbox.spec.ts`、typecheck、build、`plan_guard`、安全边界检索和 `git diff --check`。这些命令本检查点均未运行。
- C6 重启恢复改为：C2 先提供默认关闭的暂停上送，用第 7 节那一条真实入站在暂停期间落盘，杀进程后仍未确认，再放行。禁止注入通知、插库、再发一条或只测内存队列。没有这个开关则该步 `blocked`，不得假测。
- P13/B14 不是本轮只收消息的阻塞项，契约也没有把它们写成完成。B14 两份同日记录不能合成一句「真机仍 blocked_hardware」：
  - `docs/current/input-transport-20260922.md` 第 31 行是较早边界，当时真机项保持 `blocked_hardware`。
  - `artifacts/input-transport-20260922/device-acceptance/production-gate.md` 第 19 行是较晚结论：硬件准入检查点已经通过；只允许安全的 API 34 字段验收；输入功能未在闲鱼 Flutter/ColorOS 验收通过；API 29–32 均未真机验收。
  - 语义清单 `artifacts/input-transport-20260922/semantic-acceptance-checklist.md` 第 6–7 行写真机仍属 `blocked_hardware`、不在该软件清单内。那是软件门的范围句，不能覆盖第 19 行已经写下的硬件准入通过。
  - 正确口径：硬件准入已通过；输入字段真机验收未执行。本契约不把准入倒退成未开始，也不把准入写成输入功能通过。

## 未运行的检查

本检查点只改文档。没有执行：`adb devices`、`getprop`、pytest、vitest、`pnpm typecheck`、`pnpm build`、Gradle 聚焦/全量/lint/assemble、ruff、pyright、mypy、`plan_guard`、`git diff --check`、数据库查询、进度表更新。C4 清单是后续必跑命令，不是本次已通过。主会话给出的三台机型、0.1.0 安装情况和 ELE 未安装，本文件没有在本机复测。
