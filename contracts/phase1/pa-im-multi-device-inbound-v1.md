# 三机闲鱼只收不发：pa-im-m3/20260922.1

状态：契约冻结。不是软件通过，不是真机验收通过。

本文件是 `contracts/phase1/pa-im-aggregation-v1.md`（pa-im/20260913.1）的增量契约，只覆盖三台已授权物理设备上的闲鱼入站消息聚合。父契约里的人工回复 API、回复任务和发送定位器继续存在，供已有测试回归保护；本版本不启用、不扩展、不验收它们。

冻结日期：2026-09-22（Asia/Shanghai）。检查点：C1。

## 1. 三台物理设备与四个 ADB serial

生产身份只使用已绑定的 `device_id`。ADB serial 只用于验收时定位手机，不得写入线程键、幂等键、上报载荷或 Web 过滤条件。

| 逻辑设备 | ADB serial | 机型（主会话本轮 ADB 证据） | 生产身份 |
|---|---|---|---|
| OnePlus 9R，一台 | USB `b0644fb5`；Wi-Fi `192.168.5.6:5555` | `LE2100`。两个 serial 是同一实体的两条传输，只算一台 | 2026-09-22 15:50 的本机 binding 读数为 `4aabc387-6e4b-4b59-a525-b1c119ec7f5b`（`artifacts/ocr-device-gates-20260922/device-identities.json` 第 47–50 行）。C5 仍须现场再读当前 binding，不得用 serial 或旧展示名 `oneplus-9r-b0644fb5` 代替 |
| 华为，一台 | `APH0219624006517` | `HUAWEI VOG-AL10` | 只认该机当前未撤销 binding 里的 `device_id`。本文件不写死；serial 不是 `device_id` |
| 华为，一台 | `GBGDU19830002425` | `HUAWEI ELE-AL00` | 同上 |

这是三台物理设备、四个 ADB serial。验收同一时刻 OnePlus 只驱动一条传输；Wi-Fi alias 不得计成第四台。C5 开始时重新执行 `adb devices -l` 与 `getprop ro.product.model`。serial、机型与上表不一致，或 binding 读不到，该台停止。不得把缺席的设备写成另一台。

以下旧说法作废，不得再引用为身份：工作区 `项目交接说明.md` 第 135 行和 `cloudctl-source/docs/delivery/functional-delivery-progress-2026-09-01.md` 第 72 行把 `APH0219624006517` 写成「疑似 OnePlus / believed to be the OnePlus」。主会话本轮 ADB 证据已把它定为 `HUAWEI VOG-AL10`。`docs/v1/device-matrix.json` 把 serial `b0644fb5` 填进 `device_id`，也不能当生产身份。`artifacts/ocr-device-gates-20260922/device-identities.json` 在 2026-09-22 15:50 只读到 OnePlus；当时 `APH0219624006517` 与 `GBGDU19830002425` 为 `absent`，那次缺席不能否定本次主会话读数，也没有提供这两台的 `device_id`。

## 2. 只收不发

本轮范围只有外部入站文本到达 Web。明确禁止：

- 调用 `POST /api/v1/im/threads/{id}:reply`。
- 创建任何回复任务、`direction=OUT` 的新业务消息，或 `reply_task_id`。
- 在闲鱼点击发送、输入回复、或通过无障碍/IME 向闲鱼写入文本。
- 自动回复、关键词回复、改价回复、图片/表情回复。

已有回复代码（`im_routes.py` 的 `reply`、`im_service.py` 的 `reply`、`ImInboxView.vue` 的 `sendReply`、Companion 回复步骤）本轮只做回归保护：原测试继续通过，不新增发送路径，不把回复按钮接到本轮验收。C2–C6 的任何实现、测试夹具或真机步骤都不得发送闲鱼消息。

父契约「回复 = 普通受控任务」在本版本中冻结为不执行。

## 3. 生产采集通道

本轮生产只启用通知采集：

1. Companion 无障碍服务消费 `TYPE_NOTIFICATION_STATE_CHANGED`，包名 `com.taobao.idlefish`。这是本轮唯一生产通道。
2. 默认且本轮强制运行配置为 `mode=NOTIFICATION`。三台验收设备在 C6 观察开始前必须确认云端与 Companion 内存配置都是 `NOTIFICATION`。若某台当前已是 `DUTY`，先改回 `NOTIFICATION` 并确认 `tick` 不再进入值班循环；改不了就停止该台，不得带着值班模式做「只收」验收。

现有值班模式不是只读消息页，本轮不启用，也不把它改写成无动作：

- `DutyController.tick` 在 `dutyMayWrite` 为真时启动 `runCycle`（`DutyController.kt` 第 63–68 行）。
- `ensureOnMessageList` 会 `launchTargetApp` 打开闲鱼，并点击消息 tab；前台兜底还会 `tapRemoteGestureLike`（同文件第 90–117 行）。
- `openConversation` 按未读会话入口的屏幕中心点击（第 189–191 行），随后 `backToList` 调用 `dutyBack`（第 232–237 行）。

因此：不得把这条旧路径写成「只读、不启动、不点击」。不得在本轮实现里为了补采而走到上述调用。把值班改成真正只读、或单独验收 `DUTY`，都不在本版本；后续要做必须另写验收契约。C2 只须证明 `mode=NOTIFICATION` 时这些启动和点击不会执行。

明确不是生产通道，也不得为了本轮验收而启用：

- ADB（`adb shell`、`uiautomator dump`、通知历史拉取、模拟通知）。
- `NotificationListenerService`。
- 闲鱼私有数据库、应用私有目录、Root、Shizuku、Device Owner。

不需要 Root。验收时 ADB 只允许：确认 serial、安装已构建的 Companion、读取本契约要求的 Companion 日志/本地 outbox 计数。ADB 不得充当消息来源。

## 4. Android 上报与本地 outbox

每条入站上报必须带：

| 字段 | 约束 |
|---|---|
| `platform` | 本轮生产值只允许 `xianyu`。由包名映射产生，禁止客户端省略后由服务端默认补成闲鱼。 |
| `peerKey` | 通知标题去空白后的稳定串，1..128。 |
| `peerName` | 与 `peerKey` 同源的展示名，1..128。 |
| `text` | 通知或气泡原文。进入幂等键之前必须先变成第 4.1 节的同一份 canonical 文本；禁止用截断前全文算键。 |
| `occurredAt` | 通知 `when` 的 UTC 时间；缺失时用事件到达时刻，并在本地日志标记 `OCCURRED_AT_SYNTHESIZED`。 |

设备身份不放进 JSON：仍由既有 binding 认证决定 `tenant_id` + `device_id`。

本地持久 outbox（必须新做，不得继续只用 `ImMonitor` 内存 `ArrayDeque`）：

- 入队前先落本地持久存储，进程被杀后能按原 `dedupeKey` 恢复未确认项。
- 云端返回该条已被接受或明确重复后，才标记确认并移出待发集合。
- 网络失败、5xx、超时：指数退避重试，条目保持未确认。
- 4xx 契约拒绝：不得无限重试冒充成功；必须留下可查询的永久失败记录（本地计数 + 日志码），不得静默删除。
- 容量上限必须可观察。达到上限时拒绝新事件并记 `IM_OUTBOX_OVERFLOW`，同时保留已持久化未确认项。禁止用丢弃最旧项的方式腾位置。
- 内存 LRU 只能做短时去重优化，不是可靠性边界。LRU 淘汰不得导致已持久化事件丢失。

幂等原材料在设备侧与服务端必须是同一串：`deviceId|platform|peerKey|occurredAtEpochSecond|canonicalText` 的 SHA-256。`canonicalText` 按第 4.1 节，不是截断前全文。服务端用 binding 的 `device_id` 与载荷里的 `platform` 重算；客户端自报的 device id 不参与服务端键。

### 4.1 截断与幂等（设备与服务端同一口径）

当前三处不一致，超长正文不能靠短文本重投冒充幂等：

- `ImMonitor.dedupeKey`（`ImMonitor.kt` 第 20–24 行）直接哈希事件里的 `text`，不加 `TRUNCATED ` 前缀，也不先切到 2000。
- 通知入站在构造事件前 `text.take(4000)`（`CloudCtlAccessibilityService.kt` 第 235 行）。这是 Kotlin `Char` 序列的前 4000 个 UTF-16 码元，不是服务端的 2000。
- 服务端入站 schema 允许正文到 4000（`im_routes.py` 第 38 行）。`ingest` 在 `len(text) > 2000` 时先切到 2000，再拼上前缀 `TRUNCATED `，然后才调用 `_dedupe_key`（`im_service.py` 第 23、192–201 行）。Python `len` 按 Unicode 码点。已是 canonical 的正文再次提交会被再加一次前缀，从而变成另一条键。

本版本冻结的唯一算法（Android 与服务端都先得到这份文本，再算键，再落库）：

1. 长度单位是 Unicode 码点，不是 UTF-16 码元。补充平面字符（例如一个 emoji）算 1。
2. 传输上限 4000 个码点：更长的原文只保留前 4000 个码点，这一步不添加前缀。
3. 设 `body` 为第 2 步的结果。若 `body` 的码点数 ≤ 2000，`canonicalText = body`。否则 `canonicalText = "TRUNCATED " + body 的前 2000 个码点`（前缀不占用这 2000）。
4. 该函数必须幂等：`canonical(canonical(x)) = canonical(x)`。已经等于自身 canonical 形式的正文（含恰好一个 `TRUNCATED ` 前缀加 2000 个码点）不得再加前缀。
5. 设备本地去重、持久 outbox、上报 JSON 的 `text`、服务端 `_dedupe_key` 与 `text_content` 全部使用这份 `canonicalText`。禁止一侧哈希原文、另一侧哈希截断文。

由此接受的碰撞：一条本来就等于某条超长正文 canonical 形式的短正文，会与那条超长正文共用幂等键。本版本明确接受，不另加序号。

C4 必须有同一夹具在 Android 与服务端算出相同 SHA-256，至少包括：2000 个码点整、2001 个码点、超过 4000 个码点、以及正文中含一个补充平面字符且截断点落在该字符上。C6 第 7 节的重投必须覆盖超长正文，不能只做短文本。

## 5. 服务端线程隔离与幂等

线程自然键：

`tenant_id + device_id + platform + peer_key`

同昵称、不同 `platform` 必须是不同 thread。同昵称、不同 `device_id` 必须是不同 thread。禁止跨租户读取。

消息幂等键必须含 platform：

`dedupe_key = sha256(device_id|platform|peer_key|occurred_at_epoch_second|text)`

其中 `device_id` 来自 binding，`platform` 来自本条载荷且必须与线程 platform 一致。

### 与现有库的兼容

当前已上线约束（`migrations/versions/20260913_0017_im_aggregation.py`）：

- `uq_im_thread_peer` = `(tenant_id, device_id, peer_key)`，不含 `platform`。
- `im_message.dedupe_key` 全局 UNIQUE，算法目前不含 platform（`im_service.py` `_dedupe_key`）。
- 列 `im_thread.platform` 已存在，但 ingest 把新线程写成常量 `xianyu`。

本版本要求一次前向迁移，不改历史行的业务含义：

1. 迁移前断言：现有 `im_thread` 不存在同一 `(tenant_id, device_id, peer_key)` 下多个 `platform`。若断言失败，迁移中止并报告冲突行，不得自动合并或删除。
2. 删除 `uq_im_thread_peer`，新建 `uq_im_thread_platform_peer` = `(tenant_id, device_id, platform, peer_key)`。
3. 不改写已有 `dedupe_key`。新写入使用含 platform 的算法。旧行保持原键，避免把历史消息重新解释成另一条。
4. 应用层在迁移完成后拒绝缺少 `platform` 的入站载荷（422），禁止再默认补 `xianyu`。
5. `downgrade` 仅允许在「每个旧三元组仍只有一个 platform」时恢复旧唯一约束；否则拒绝降级。不提供删除消息来换降级。

查询 `list_threads` / `list_messages` 必须继续按 `tenant_id` 限制；线程定位必须带 platform，不能只靠 peer_key。

## 6. Web

`ImInboxView` 在本版本必须同时满足：

- 默认「全部设备」：不传 `deviceId` 时展示当前租户全设备线程。
- 设备过滤：按生产 `device_id` 过滤，选项来自设备列表与线程中出现的设备，不用 ADB serial。
- 最近正文：列表直接显示服务端 `lastMessageText`（该线程最新一条入站或已存在消息的文本，最长展示截断由 UI 做，键值用全文）。空列表项显示「暂无正文」，不得把「摘要待补全」当作有正文。
- 未读：显示 `unreadCount`；既有「只看未读」保留。打开线程后的已读标记只改未读计数，不创建回复。
- 页面可见时短轮询线程列表，间隔 5 秒，抖动不超过 1 秒。选中会话在刷新后按 thread id 保持；该会话消息流以不短于列表的间隔刷新。
- `document.visibilityState !== 'visible'` 时停止轮询，恢复可见后再拉一次。组件卸载必须清理计时器。
- 这是对新轮询的要求，不是当前行为。当前 `ImInboxView.vue` 没有短轮询。现有 `refreshThreads` 只有在列表请求成功且选中 id 不在新列表中时才把 `selected` 置空（第 52–54 行）；`catch` 只写错误文案，不会清空 `selected`（第 56–58 行）。新轮询失败时必须同样不清空已有列表、不重置选中会话，并只显示错误。不得把现有 `catch` 写成已经实现了失败轮询保持。

本轮不要求 WebSocket。不要求回复框可用；回复控件保持不可作为验收路径。若控件仍渲染，验收记录必须写明「未点击」。

## 7. 三机真实验收

C6 才是真机验收。三台都要有证据，缺任意一台不得把 D 列写成「验收通过」。

每台物理设备：

1. 由外部账号发送一条该机唯一的入站文本（三台文本互不相同，且与库中近 24 小时文本不重复）。
2. 证据链四段都要留下：通知被 Companion 观察到 → 本地持久 outbox 出现未确认项 → 云端该 `device_id` 下独立 thread 与一条 message → Web 在无手工刷新下自动出现该正文。
3. 重投必须同时覆盖短文本和超长文本，只做短文本不得通过。短文本：相同 platform、peer、秒级时间桶、原文，云端 message 行数不增加。超长文本：至少在一台设备上重投一条超过 2000 个 Unicode 码点、且含一个补充平面字符的正文；第一次与第二次都走第 4.1 节 canonical 文本。以原文重投、以及以已经 canonical 的正文重投，message 行数都不得增加，接口计为重复。短文本通过不能代替这一条。
4. 受控进程重启只验证「已持久化且未确认」的同一条真实入站，不另发一条消息，也不伪造通知。做法见第 7.1 节。做不到就记 `blocked`，不得用短文本上送成功代替，也不得把未做写成通过。
5. 三台同时在线观察至少 30 分钟（Asia/Shanghai 起止时刻写入证据）。观察窗口内不得调用 reply、不得点击闲鱼发送。

OnePlus 只记一台。若 USB 与 Wi-Fi serial 同时在线，证据里写明使用了哪一条，另一条未驱动。

### 7.1 如何形成「已持久化、未确认」

当前代码没有这个状态：`ImMonitor` 队列在内存里，`deliverImEvents` 失败只是 `requeue` 回内存（`ImMonitor.kt` 第 116–155 行，`CompanionSyncService.kt` 第 561–580 行）。进程一死，未确认项就没了。所以 C6 不能用现状假装做完重启恢复。

C2 必须增加一个操作者可见、默认关闭的「暂停上送」：

- 只暂停 IM outbox 的发送；不制造通知，不写闲鱼，不点发送，不调用 reply。
- 暂停期间新的真实入站仍先落本地持久 outbox，状态保持未确认。
- 暂停标志和未确认项都要能熬过 Companion 进程死亡，并有日志 `IM_OUTBOX_HOLD`。
- 没有这个开关，或者它只存在于内存，第 4 步直接 `blocked`。

C6 在每台上按这个顺序做，全程不追加第二条入站、不从手机向外发消息：

1. 确认该机是 `NOTIFICATION`，然后打开暂停上送，留下日志。
2. 使用第 7 节第 1 步那一条外部入站，让它在暂停期间到达。这条入站是收消息证据本身，不是为重启另发的一条。
3. 核对本地持久 outbox 里该条为未确认，且云端还没有对应 message 行。
4. 只结束 Companion 进程再拉起。暂停必须仍在，同一未确认项必须还在，云端行数仍然不增加。
5. 关闭暂停。云端只出现这一行。再次重启或再次放行不得变成两行。

下列做法都是伪造或假测，命中任一项即本步 `blocked`，整台不得验收通过：`adb` 注入通知、`dumpsys` 回放当消息来源、手工往 outbox 数据库插行、用 Root 改闲鱼数据、为了制造未确认状态再发一条消息、或只在内存队列里杀进程。三台各自做；一台 `blocked` 不能由另外两台通过来填。

## 8. P13 / B14 输入通道

当前 P13（页面定位器采样）与 B14（受控输入通道）保持原状态。它们不是本轮「只收消息」的阻塞项。本契约不修改输入法切换、无障碍输入编辑器、价格九键或发送证明。C6 即使三机收消息通过，P13/B14 的进度列仍维持原值。

B14 在 2026-09-22 有两份不能混读的记录：

- `docs/current/input-transport-20260922.md` 第 31 行是同日较早边界：当时写明真机项保持 `blocked_hardware`，未取得生产租约和实体空闲证明前不驱动手机。
- `artifacts/input-transport-20260922/device-acceptance/production-gate.md` 第 19 行是同日较晚结论：硬件准入检查点已经通过，只允许安全的 API 34 真机字段验收；不能代表输入功能已在闲鱼 Flutter/ColorOS 验收通过；API 29–32 均未真机验收。

本契约同时承认这两句：硬件准入已经通过；输入字段的真机验收没有执行，不得写成输入功能通过，也不得把后来的准入倒退成「真机仍未开始」。软件语义清单（`artifacts/input-transport-20260922/semantic-acceptance-checklist.md`）同样不是输入功能真机通过。

## 9. 后续检查点：范围与停止条件

### C2 Android

允许修改：

- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/im/**`
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/service/CompanionSyncService.kt`（仅 IM 上送/配置刷新）
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/automation/CloudCtlAccessibilityService.kt`（仅通知入站提取）
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/network/CloudTaskClient.kt`（仅 IM 上送字段）
- `mobile/companion/app/src/main/java/com/company/cloudctl/companion/data/**`（仅 IM 持久 outbox）
- 上述文件的直接单元测试

停止条件：出现回复步骤、点击发送、IME 写入、调用 `DutyController` 的 `launchTargetApp` / 消息 tab 点击 / 会话入口点击、把 `DUTY` 设为验收配置、Root/ADB/NotificationListener/闲鱼数据库采集、改动 P13/B14 输入通道文件，或只改一侧截断让另一侧仍用原文算键。停止后不继续「顺手修好」。值班点击路径本轮保持不启用，不在 C2 里改成只读实现。

### C3 后端 / Web

允许修改：

- `services/control-api/src/cloudctl_api/im_routes.py`
- `services/control-api/src/cloudctl_api/im_service.py`
- `services/control-api/src/cloudctl_api/db.py`（仅 IM 模型）
- `services/control-api/migrations/versions/` 下一条新的 IM 迁移
- `tests/integration/test_im_aggregation.py`
- `tests/integration/test_im_fleet_ownership.py`
- `apps/web/src/api/im.ts`
- `apps/web/src/views/ImInboxView.vue`
- `apps/web/tests/im-*.spec.ts`

停止条件：新回复行为、跨租户查询、缺少 platform 仍默认 `xianyu`、迁移会删除或合并历史线程、或修改非 IM 路由。

### C4 质量门

C1 没有跑这些命令。C4 必须逐条实跑并记下命令、退出码和测试数。少跑一条就写「未运行」，不得把聚焦测试写成全量，也不得把全量写成已覆盖真机。

Android，在 `mobile/companion` 下按这个顺序：

1. 聚焦 IM：`./gradlew :app:testDebugUnitTest --tests 'com.company.cloudctl.companion.im.*'`
2. 全量 JVM：`./gradlew :app:testDebugUnitTest`
3. `./gradlew :app:lintDebug`
4. `./gradlew :app:assembleDebug`

第 1 步通过不能代替第 2 步。第 4 步只证明 debug APK 能编出，不是安装，也不是真机通过。

后端，在 `cloudctl-source` 下：

- `pytest -q tests/integration/test_im_aggregation.py tests/integration/test_im_fleet_ownership.py`
- 受影响文件的格式门：`ruff format --check` 与 `ruff check`，路径至少包括改动过的 `services/control-api/src/cloudctl_api/im_routes.py`、`im_service.py`、`db.py`、新迁移，以及上面两个测试文件。
- 受影响文件的类型门：`pyright` 与 `mypy`，同一批 Python 路径。工具不接受单文件时改跑仓库既有入口（`Makefile` 的 `typecheck` 前半是 `pyright` 然后 `mypy`），并写明实际命令。

Web，在 `apps/web`：

- `pnpm exec vitest run tests/im-inbox.spec.ts`
- `pnpm typecheck`（`package.json` 里是 `vue-tsc -b`）
- `pnpm build`（`vue-tsc -b && vite build`）

C3 若还改了 `tests/im-api.spec.ts`、`tests/im-outbox.spec.ts` 或 `tests/im-reply-boundary.spec.ts`，这些文件也要跑。只跑 `im-inbox.spec.ts` 不能代替被改过的其它规格。

另外三条：

- `python scripts/plan_guard.py docs/current/tasks.json`。这只审计该计划文件的静态图，不是本契约已实现的证明；失败或未包含本任务时照实记录，禁止为了通过去改计划状态冒充验收。
- 安全边界核对：对本次 diff 检索 reply 调用、`DUTY` 被写成验收默认、`settings put secure`、`pm uninstall`、`pm clear`、通知注入和 Root。命中第 2、3、7.1 节禁止项即 C4 失败。
- `git diff --check`

停止条件：删掉失败用例、放宽幂等、只交聚焦测试、或把未跑的命令写成通过。

### C5 人工授权与接入

不改仓库代码，不发消息，不调用 reply，不点闲鱼发送。C5 允许的设备动作只有：核对签名与 binding、同签名覆盖升级、ELE 首次安装。无障碍和华为后台常驻只能由用户在手机上手工打开。

先读现场，再动安装：

- `adb devices -l` 与每台 `adb -s <serial> shell getprop ro.product.model`，结果必须仍是第 1 节那三台。
- 每台用 `-s <serial>` 读 `com.company.cloudctl.companion` 的已装版本和签名证书，并与待装 APK 的签名证书比对。本轮主会话证据：`APH0219624006517`（VOG）与 OnePlus 当前是 Companion 0.1.0；`GBGDU19830002425`（ELE）当前未安装。OnePlus 的 0.1.0 也能在 15:50 的 `device-identities.json` 第 36–45 行对上。C5 以当场 dumpsys 为准；和这句话不一致就停止并记录，不得按旧话安装。
- 已安装且签名证书一致：覆盖升级，保留数据。签名不一致：停止。不得 `pm uninstall`，不得 `pm clear`，不得清数据后再装。
- ELE 当场确认未安装：允许首次安装。若当场其实已安装，改按上一条比对签名，不得当成首次安装覆盖。
- 安装或升级之后，用户自己在系统设置里开启无障碍。两台华为的后台常驻也由用户手工开启。禁止 `settings put secure`、`appops` 或其它静默写法替用户打开。
- 每台再读 Companion binding 里的 `device_id` 并写入证据。VOG 与 ELE 没有可以抄的生产 id；OnePlus 也要复读，不能只抄 `4aabc387-6e4b-4b59-a525-b1c119ec7f5b`。读不到 binding 的设备不进入 C6。

操作者确认手机无人使用，并留下「只收不发、不点发送」的授权。缺 serial、机型、签名比对、binding 或人工授权任一项，C5 停止。

### C6 真机验收

只在 C5 完成且三台 binding 都已记录之后，按第 7 节和第 7.1 节取证。停止条件：任一设备缺四段证据、重启恢复步为 `blocked` 或未做、30 分钟观察不足、发现本机向外发送或点击发送、OnePlus 两个 serial 被计成两台、机型与第 1 节不符、或需要 Root、卸载清数据、静默改 secure settings、ADB 注入通知才能看到消息。任一命中，结论只能是未通过，并写明缺哪一台。

## 10. 本检查点不做

- 不改 xlsx 进度表。
- 不改生产配置、不重启服务、不连接手机、不安装 APK。
- 不实现 C2/C3 代码。
- 不把本文件的存在解释为模块通过或验收通过。
