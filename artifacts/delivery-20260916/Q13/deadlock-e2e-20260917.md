# FLEET-22 死锁 E2E（A 机）— 2026-09-17 14:15 CST 通过

场景：RUNNING（wait-home）→ POST `:pause` → PAUSED_WAITING_USER → POST `:cancel` → 本地 60s 内 SERVER_TERMINAL 退役 → 同机探针可认领。

设备 A：`b0644fb5` / deviceId `4aabc387-6e4b-4b59-a525-b1c119ec7f5b`，租户 `00000000-0000-7000-8000-000000001111`，账号 `01a07a1c-572c-7ed5-83ad-a48ebbfed67a` bindingVersion=1。生产 a14-88b4c78 + B17 APK。未 `am force-stop` companion。

## 任务 dbaf3763-e894-452b-9f63-3494f0775e43

Idempotency-Key：`q14-deadlock-publish-A-1`  
commandType：`xianyu.publish_listing.v1`（wait-home 挂起窗；未点发布）

| 时刻 (UTC) | 事件 |
|---|---|
| 06:14:17.724 | QUEUED / created |
| 06:14:17.966 | RUNNING / startedAt |
| 06:14:18.310 | 本地 TASK_CLAIMED_LOCAL |
| 06:14:20.420 | 本地 wait-home STEP_STARTED |
| 06:14:40.553 | POST `:pause` 200 → PAUSE_REQUESTED rev1 |
| 06:14:43.896 | 本地 PAUSED_WAITING_USER |
| 06:14:44.059 | 服务端 PAUSED_WAITING_USER，pauseAckAt 已写（pause 后约 4s） |
| 06:15:22.863 | POST `:cancel` 200 → 立即 CANCELLED rev2（PAUSED 取消不走 CANCEL_REQUESTED） |
| 06:15:23.873 | 本地 run_journal FAILED / SERVER_TERMINAL（cancel 后约 1s，远小于 60s） |
| 06:15:24.930 | 本地 inbox TERMINAL_REJECTED / FAILED |

controlEvents：

1. rev1 PAUSE_REQUESTED `q14 deadlock E2E pause while RUNNING on wait-home`
2. rev2 CANCELLED `q14 deadlock E2E cancel after PAUSED_WAITING_USER`

HTTPS 公网重放 `:cancel` 幂等 200 CANCELLED。zsh 须给 `".../${TID}:cancel"` 加引号，否则 `$VAR:cancel` 被当成历史修饰符，看起来像 405。

## 探针 0ebe2805-f1c0-447a-b61b-dfa4a1659fd9

Idempotency-Key：`q14-probe-A-after-deadlock-1`  
commandType：`device.probe_capabilities.v1`

- 06:16:21.512 QUEUED
- 06:16:24.192 startedAt
- 06:16:28.081 SUCCEEDED（cancel 后约 65s 内同机新任务跑通）
- 本地 inbox TERMINAL_CONFIRMED / SUCCEEDED @ 06:16:28.305

cancel 后本地无 PAUSED/RESUME_CHECK/RECONCILING 阻塞头。队列已恢复。

## 本地 journal

见 `publish-draft/A_run_journal_dbaf3763.txt`：

```
TASK_CLAIMED_LOCAL  06:14:18.309640Z
wait-home STARTED   06:14:20.419521Z
CHECKPOINT_1        06:14:43.886682Z
PAUSED_WAITING_USER 06:14:43.896017Z
FAILED SERVER_TERMINAL 06:15:23.873398Z
```

## 结论

A14 heartbeat `blockingTask` / B17 控制面不经 execution gate 的热修，在 A 机真机上闭合：PAUSED 镜像 + 服务器终态 → 自动收敛，不永久卡队列。FLEET-20（wait-home 无主动回首页）与 FLEET-21（执行旁路不落 journal）仍归 B 线，本 E2E 不覆盖。
