# 双线扩展交付 — 2026-09-13（IM 聚合 + 实时观看/远控）

背景：用户决定并行推进「消息聚合（原二期提前）」与「投屏/远控（P10/P11）」。
委派子智能体因模型服务持续 503（5 轮）不可用，按规则报告 SUBAGENT_CAPABILITY_UNAVAILABLE
后由 Root 亲自实现两线，均走独立 worktree（pa-im / pa-live）后集成分支合并。

## 线 1：IM 消息聚合 slice 1（pa-im/20260913.1）— 已集成

- 后端：迁移 20260913_0017（im_thread/im_message）；im_service/im_routes
  （companion 批量上报幂等、threads/messages/mark-read/reply）；reply 生成 6 步受控任务
  （含新步骤类型 ui.tapText）；同会话 60s 限流 + 设备忙拒绝。
- Android：通知监听（仅闲鱼）→ LRU 去重 → 批量推送（不阻塞任务循环）；
  ui.tapText 解析/执行（唯一可见文本节点才点击，否则 TAP_TEXT_NOT_UNIQUE）；
  3 个新会话定位器（锚点待真机复核）。
- Web：/im 消息收件箱（会话列表/未读角标/消息流/回复框，409 语义展示）。
- 门禁：后端 6 用例（幂等/归并/回复任务可领取/限流/忙/schema）、Android 194 单测、web build。

## 线 2：实时观看/远控 slice 1（p10-live/20260913.1）— 已集成

- 服务端 live.py：内存会话状态机 VIEWING/REMOTE/CLOSED；REST 全套 + 双 WS
  （operator 帧/输入流、companion 帧上行）；30min 硬超时+30s 无帧宽限惰性清算；
  输入 seq 单调 + 10/s 限速（违规断 REMOTE）；REMOTE 期间 claim 409 DEVICE_REMOTE；
  帧不落盘；全迁移审计 live.session.*。
- Android：MediaProjection 前台服务（Manifest 声明）采集 ≤720/q60/5fps（观看 1fps）；
  OkHttp WS + 证书 pinning 复用；远控输入仅 REMOTE、seq 本地校验、手势走无障碍通道
  （禁 shell input）。
- Web：DeviceDetailView 挂 DeviceLivePanel（开看/接管/交还/停止、帧渲染、
  REMOTE 画布 tap/swipe、客户端 10/s 限速）。
- 门禁：后端 5 用例（状态机/审计/重复开看/claim 拒绝/seq/限速纯函数）、
  Android 197 单测、web typecheck+build。

## 集成结果（分支 integration/p14-20260909，已推送）

- 合并提交：1856783（IM）、5136804 前身 7eb9f12（live）+ 接线 37853b5。
- 集成回归：后端 51 passed / 1 skipped（IM+live+P09 账本）；Android 197/0；web build ✓。
- 传输说明：slice 1 用受控 WS JPEG 帧流（同源+pinning）；WebRTC/TURN（D03）为后续升级，
  会话语义与传输解耦。

## 未完成 / 待真机（Root 持 DEVICE 锁后执行）

1. IM：真闲鱼通知→Web 收件箱端到端；3 个会话定位器真机复核；回复任务真机送达。
2. Live：真投屏授权流程、帧率/画质实测、接管时任务暂停联动、30 分钟上限实测（Q04 前置）。
3. 后续切片：自动回复引擎（slice 2）、WebRTC+TURN（D03）、跨平台消息。
4. 运维：服务端迁移 0017 需在部署时执行；live 依赖 uvicorn WS（部署配置确认）。
