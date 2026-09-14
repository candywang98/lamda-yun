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
