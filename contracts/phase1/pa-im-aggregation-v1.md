# IM aggregation slice 1: pa-im/20260913.1 (scope addition, user-approved)

用户 2026-09-13 决定将原二期的「聚合聊天」提前。Slice 1 只做：闲鱼消息
监听→云端聚合→Web 查看→人工回复下发。**不含**关键词自动回复、改价回复、
图片消息回复、小红书/抖音消息（slice 2+）。

## 数据模型（唯一迁移，持有 DB_MIGRATION 锁）

- `im_thread(tenant_id, device_id, platform, peer_key, peer_name, last_message_at,
  last_direction, unread_count, created_at, updated_at)`；唯一键 (tenant_id, device_id, peer_key)。
  peer_key = 闲鱼会话对方昵称（notification title 去重后的稳定串）。
- `im_message(id, tenant_id, thread_id, direction IN|OUT, content_type TEXT|SYSTEM,
  text_content, occurred_at, dedupe_key UNIQUE, reply_task_id NULL, created_at)`。
  dedupe_key = sha256(device_id|peer_key|occurred_at_bucket|text) ；occurred_at_bucket 取
  notification 的 whenTimestamp 秒级。

## Companion → 云端 API

- `POST /companion/v2/im/messages`（binding 认证，数组，幂等按 dedupe_key，
  单批 ≤20 条，单条 text ≤2000 字符，超出截断标记 TRUNCATED 前缀）。
- 推送通道复用 event_outbox 机制（新 path 类型 im.messages），断网排队重试，不阻塞任务循环。

## 监听（Android，闲鱼 slice 1）

- CloudCtlAccessibilityService 开启 `TYPE_NOTIFICATION_STATE_CHANGED` 事件；
  仅处理 `com.taobao.idlefish` 的通知：取 title(=peer_name)、text(=消息内容)、
  when、ticker 为空则用 text。自己发的消息（回复任务发出的）不回推（direction=OUT
  由 reply 流程写，不由通知产生）。
- 去重：内存 LRU(dedupe_key) + 服务端唯一键双保险。
- 敏感与风控：不上传通知里的验证码类内容不做识别（slice 1 全量上报，运营侧自查）；
  不点击通知、不读通知历史，只消费事件流。

## 操作员 API

- `GET /api/v1/im/threads?deviceId=&unread=`（列表，按 last_message_at desc，分页 after/limit≤50）
- `GET /api/v1/im/threads/{id}/messages?after=&limit=`（时间正序）
- `POST /api/v1/im/threads/{id}:mark-read`
- `POST /api/v1/im/threads/{id}:reply {text}`（≤500 字符，生成 mobile task，见下）
- 限流：同 thread 60 秒内最多 1 条回复（409 THREAD_REPLY_RATE_LIMITED）；
  thread 所在设备存在 RUNNING/RECONCILING 任务时拒绝（409 DEVICE_BUSY）。

## 回复 = 普通受控任务（复用现有执行器，不加新门禁类型）

reply 生成 legacy steps 任务（targetPackage 闲鱼）：
1. tap `xianyu_messages_tab`（新注册定位器，desc「消息」）
2. `ui.tapText {value: peer_name}`（**新步骤类型**，见下）
3. wait `xianyu_chat_input`（新定位器，desc 前缀「发送消息」或等价输入框锚）
4. input `xianyu_chat_input` {value: 回复文本}
5. tap `xianyu_chat_send`（新定位器）
- `ui.tapText`：新增 MobileStep 判别 action=`ui.tapText`，字段 `value`(1..64)；
  语义=在目标包内找 text 或 content-desc 与 value 相等且可见的唯一节点并点击；
  0 或 >1 匹配即失败（TAP_TEXT_NOT_UNIQUE），不加坐标猜测。服务端 schema 同步放行该 action。
- 输入走现有闲鱼路径（IME）；发布门禁不涉及（发消息不是 click-publish）。
- 回复任务 ID 回写 im_message.reply_task_id；任务终态回写 thread.last_direction=OUT。

## Web（slice 1 最小）

- 新视图 ImInboxView：左会话列表（未读角标、设备过滤），右消息流 + 输入框 + 发送按钮
  （调 :reply，显示生成的任务 ID 与限流错误）；不做的：图片、表情、快捷短语、移动端适配。
- 路由注册、导航入口由 Root 集成时接线（worker 不改 OperationsShell/路由表共享文件）。

## 边界与不做

- 不做自动回复引擎、不做跨平台、不做消息删除（P36 另算）、不绕过 Companion 直连手机。
- Companion 端不新增对外端口；全部走既有 pinned HTTPS。
- 验收：后端 pytest（含幂等/限流/忙碌拒绝/tapText schema）；Android 单测（解析器 tapText、
  通知提取去重）；Web typecheck/build。真机验收（真通知→Web 可见→回复送达）由 Root 持 DEVICE 锁执行。
