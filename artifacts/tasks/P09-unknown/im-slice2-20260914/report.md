# IM slice 2 + 集成基线修复 + 值班模式安全修复 — 2026-09-14

基线：`9ba6119`（基线修复）← `8985945`。最终集成 HEAD：`56ee311`（已推送 origin/integration/p14-20260909）。
设备：OnePlus 9R `b0644fb5`（Companion debug APK，`ec62b79`/`45f9a3f`/`56ee311` 逐轮升级安装，无障碍全程保持开启）。服务端：首尔 `pa-dual-02a10fd`（未变更部署）。

## 一、基线修复（控制器，`9ba6119` + `7395a6f`）

全仓测试从 7 失败恢复全绿，均为过时断言/死代码/环境问题，无产品回归：

| 失败 | 根因 | 处置 |
|---|---|---|
| OpenAPI 契约不一致 | 3d2759f 增端点后未再生成 | 控制器统一再生成 |
| media upload URL | 已改为 API 相对路径契约 | 断言更新为新契约 |
| 商品派发 steps 索引 | 新增 ui.wait 前置步移位 | 按 stepId 定位 |
| P14 engine=2 被拒断言 | CURRENT_ENGINE_VERSION 已升至 2（G3 门禁需要） | 改为 engine=3 拒绝 |
| WSS 测试 ImportError | macOS 系统代理污染本地回环连接 | `proxy=None` |
| 无动态执行安全测试 | 535a22b 遗留死代码 `shellTap`（Runtime.exec，未被调用） | 删除 |

修复后：后端 555 passed/1 skipped；Android 201/0/0；Web 139/139。

## 二、三个并行切片（隔离工作树，同一基线 SHA）

| 切片 | 分支/提交 | 范围 | 测试 |
|---|---|---|---|
| Web 监控配置 UI（值班模式/平台多选/DM 通道/只读角色/保存反馈/摘要占位） | agent/web-monitor-ui `ea15dd4` | apps/web | 155/155 + vue-tsc 0 错 |
| 微信公众号 publisher 骨架（草稿/发布门禁/状态轮询/审计/fake transport 零真实网络） | agent/wechat-publisher `ef81fe0`（迁移 20260915_0019，down→0018） | services/control-api | 专项 10/10；全量 565 passed/1 skipped |
| Android IM slice 2（导航复位原语/会话正文回填/滚动定位/相册内容寻址 upsert） | agent/im-slice2-android `b631037` | mobile/companion | 224/0/0 |

集成顺序：web → 后端(含迁移) → OpenAPI 再生成一次（`ec62b79`）→ Android；同一 SHA 三端复跑全绿。

## 三、真机验收发现并修复的两个真缺陷（控制器持 DEVICE 锁）

### 1. 值班模式单写者违规（`45f9a3f`）

把监控配置切到 DUTY 后，`DutyController.tick` 仅对「暂停/核对中」让位（`hasBlockingHead` 不含 RUNNING），回复任务执行中被值班导航（重启闲鱼+坐标点击）打断：输入被清空→发送步 STEP_TIMEOUT；且 `ensureOnMessageList` 节流条件写反（不在消息列表时每 tick 都导航），形成 ~6s 重启循环。
修复：`AutomationStore.hasActiveTask()`（RUNNING+PAUSED+RESUME_CHECK+RECONCILING+未解除动作）+ 纯时间间隔节流。新增单测；装新 APK 后循环消失。
**复验：DUTY 模式下回复任务 `31568cd7` 6 步全部 SUCCEEDED（19:30:57），消息真实送达。**

### 2. 聊天输入走描述字段回退链导致垃圾外发（`56ee311`）

失败任务期间发现 lucas 会话收到 1 条十六进制串（64 位哈希×3）与 1 条「2」——描述字段的多重回退（剪贴板播种+长按粘贴）在聊天输入上追加脏内容，叠加值班坐标点击键盘区域被发出。
修复：`xianyu_chat_input` 专用提交路径（手势点击激活→SET_TEXT→节点文本校验，失败即抛 INPUT_REJECTED 安全终止；无剪贴板/无粘贴/无偏移手势）。

## 四、遗留缺口（如实登记，不冒充完成）

1. **聊天输入 SET_TEXT 可靠性**：搜狗输入法占用输入连接时 SET_TEXT 不落入 Flutter 聊天框（本轮 3 次 INPUT_REJECTED，全部零副作用安全失败）。历史成功（09-14 10:36 `8a5ead36`、19:30 `31568cd7`）说明该路径时好时坏。**正确修法**：聊天提交强制走 CloudCtlInputMethod（自有输入法）通道，属独立工作项。在新修复落地前，回复任务失败安全、不会外发垃圾。
2. **失败回复任务的 OUT 消息行**：服务端在派发时即记录 OUT 消息，任务 FAILED 后未回撤/标记，与真实送达不可区分——需服务端按任务终态回写 OUT 消息状态。
3. 值班导航固定坐标 (975,2331) 在键盘开启时不可靠——已通过让位+节流缓解，根治应改为锚点定位。
4. lucas 测试会话本轮共收到 3 条真实消息（1 条正常回复「在的，可以直接拍下」+ 1 条 hex + 1 条「2」），均为验收窗口内测试账号；已停用 DUTY 模式遏制。
5. MediaStore upsert、正文回填真机效果、监控配置行为级（非同步级）验证：本轮未覆盖，待下一验收窗口。

## 五、门禁与运维

- 后端 565 passed / 1 skipped；Android 225/0/0（新增 hasActiveTask 用例）；Web 155/155。
- 安全复查：mobile 无禁用 API；65000 端口仅 lamda-driver 使用、edge-hub 显式拒绝；wechat appSecret 为 SecretStr 加密存储不回显。
- 对抗性审查：code-reviewer 因轮次上限未出完整报告（Android 执行器逻辑已确认无发现问题）；完整审查待补。
- 生产服务未重启未重新部署（本轮后端改动不影响已部署行为；wechat 端点待下次部署窗口）。

## 六、追加：聊天输入阻塞已闭环（专家会诊 + 控制器三轮真机迭代，2026-09-14 晚）

升级流程：控制器三次攻坚失败（INPUT_REJECTED）→ 按升级规则交给专家智能体（gpt-6-astra）→ 专家给出根因与自有 IME 通道实现（`d628c41`，248 测试）→ 控制器真机验收又发现三层真机事实并各修一轮：

1. **绑定门禁错位**（`fefcee9`）：键盘弹起后焦点节点在 IME 窗口而非应用子树，子树焦点门禁饿死绑定循环——改为包名作用域会话绑定。
2. **快照契约过严**（`99e2ccc`）：Flutter 不实现 getExtractedText / 返回平台默认 partial 偏移 0（非文档 -1 哨兵），严格契约拒绝一切提交——降级为光标窗口精确读写；空输入框免 setSelection 直接 commitText（选区变更正是诱发编辑器重启的触发器）。
3. **编辑器会话抖动**（`6c30b94`）：闲鱼聊天编辑器约每秒重启会话，绑定到濒死会话的提交被吞——加稳定窗（会话连续存活才写）+ 等待期重开键盘 + 提交后经活跃会话回读。

**最终真机验收通过**：任务 `dccf9457` 六步 SUCCEEDED；事件链 `CHAT_IME_WAIT_CONNECTION → CHAT_IME_COMMIT_ONCE → CHAT_IME_VERIFIED`（68ms 确认）；屏幕终验最新气泡逐字等于回复文案、无乱码无重复；Android 251 测试 0 失败。

**运行前提（产品语义，非缺陷）**：IM 自动回复任务要求 CloudCtl Input 为当前输入法（应用内会引导选择；未选中时任务 INPUT_IME_REQUIRED 安全失败，零副作用）。验收后已把设备输入法恢复为搜狗。

缺口 1 就此关闭；其余缺口（OUT 消息行回撤、值班锚点定位、三项行为级验证、完整对抗审查）不变。

## 七、追加第二轮（2026-09-14 深夜）：行为级验证、缺口批量关闭

并行推进（4 写入子智能体 + 2 拆分审查员 + 控制器真机验证），集成 HEAD 推进至本次收尾提交：

| 事项 | 结果 |
|---|---|
| **正文回填闭环**（缺口4之一） | ✅ 真机通过：闲鱼全页文本仅走 content-desc（node.text 全空，JVM 测不出的真机事实）；气泡=可滚动列表内 clickable 节点；坐标从列表 bounds 派生（键盘压缩场景实测）。任务后 1 次下拉即读到对方消息，云端 IN 新行=「这个多少钱」（lucas 真实文本）。attempt=1 inbound=true queued=true |
| **监控配置行为级验证**（缺口4之一） | ✅ DUTY 值班内：tick 每 45s、锚点优先、坐标兜底打点（DUTY_NAV_COORD_FALLBACK）、未落地告警、零误输入；值班外（03:00-04:00）：40 秒完全静默；已恢复 NOTIFICATION |
| **值班导航锚点化**（缺口3） | ✅ agent/duty-anchor：DutyMessageListNav 锚点优先+有界坐标兜底+前台校验；真机聊天页场景实证锚点缺失时安全兜底 |
| **失败回复 OUT 行回撤**（缺口2） | ✅ agent/im-out-retract：im_message.delivery_state（PENDING/DELIVERED/FAILED，DB CHECK），任务终态幂等单向联动，历史回填 DELIVERED，迁移 0020；574 passed |
| **完整对抗审查**（缺口5） | ✅ 拆分两路完成：Android 五项全过（可部署）；后端/Web 发现 2 应修——均已由 agent/im-route-permissions 修复（IM 写端点服务端 device.control 权限 403 矩阵实测；appSecret 生产 Fernet 强制+测试覆盖），579 passed |
| 缺陷期垃圾数据清理 | ✅ 生产库删除 2 条回填垃圾（语音按钮/系统提示）+ 2 个营销推送假线程；lucas 线程仅存真实数据 |

**新发现缺口（登记待办）**：
1. **闲鱼营销推送制造假会话**：广告推送（「全场支持验货保真…」「附近上新…」）经通知通道进入 im_thread 成为假 peer——8985945 的 DM 过滤对闲鱼放行全部通道。需要按通知渠道/标题模式过滤闲鱼非私信推送（服务端或 Android 侧）。
2. 值班导航从内页（如聊天页）出发时锚点必然缺失，应先有限次返回再找锚点（当前安全兜底但导航不生效）。
3. MediaStore upsert 去重的真机行为级验证仍未做（需媒体导出任务，未在本轮窗口）。
4. 审查建议：气泡读取整树兜底加文本黑名单；固定坐标加分辨率守卫（换机失效表现为静默失败）；:mark-read 是否收紧另议。
5. 公众号 publisher 部署：用户已明确搁置（含 CLOUDCTL_WECHAT_SECRET_ENCRYPTION_KEY 生产配置项，已写入 runbook）。

## 八、追加第三轮（2026-09-14 深夜收尾）：upsert 闭环、噪声过滤、值班停驻

| 事项 | 结果 |
|---|---|
| **MediaStore upsert 真机闭环**（缺口4最后一项） | ✅ 连续 8 次同资产导出任务定位出**双根因**：① RELATIVE_PATH 需尾斜杠；② **insert 时系统按 MIME 自动补 `.jpg` 扩展名，查询用裸资产名永不命中**——统一 displayName（含扩展名）后终验 `existing=1 decision=Reuse`、行数零增长。验证遗留副本已清空（相册 0 行）。决策/异常日志已留 `gallery upsert` 打点 |
| **闲鱼营销推送过滤**（新缺口1） | ✅ agent/im-feed-noise `ce8b7cd`：分层防御——通道层（未标定态保持中性，需真机抓 IM_NOTIF 日志标定 channel 后启用）+ 形态层（peer 名>16 字/含换行/含营销关键词即丢弃，双生产样本形态覆盖）；IM_NOTIF/IM_FEED_DROPPED 审计打点。真机标定待后续推送窗口 |
| **消息 tab 多形态锚点** | ✅ 三形态（未读前缀/未选中/选中），「闲鱼，」不误配；回复任务有未读场景命中集合严格不变（测试论证） |
| **值班停驻三连修**（真机逐层实证） | ✅ ① 内页先返回再锚点（DUTY_NAV_BACK ≤2 次）；② 「未选中」形态在任何带 tab 栏的页面都存在——停驻判定收紧为选中形态/未读+isSelected；③ **消息列表页 tab bar 根本不在 semantics 树**——补会话条目内容特征（时间戳/红点提醒）作停驻证据。终验：首页出发锚点直击、内页 1 返回后命中、停驻后 105 秒完全静默、全程零坐标兜底 |
| 测试基线 | Android 274/0/0（+12）；后端 579/1 维持；Web 155 维持 |

**新登记待办**：
1. XHS NAV_RESET_FAILED：小红书从内页（编辑页）回不到根——rootAnchorRefs 的 xhs 锚点在内页不可见 + Flutter 恢复路由；本轮 upsert 验证任务 2/3 均失败于此（不影响 upsert 结论，导出在 preflight 已完成）。需为 xhs 补内页退出策略（独立工作项）。
2. 营销过滤通道层标定：等下一条真实 feed 推送到达时抓 IM_NOTIF 的 channel id 填入白/黑名单。
3. 相册导出行清理策略：MediaDeliveryCoordinator 成功任务后有删除清理路径，失败任务遗留行需确认清理时机（本轮验证已手工清空）。
