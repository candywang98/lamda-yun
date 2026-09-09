# P08 暂停→人工→同 taskId 恢复

日期：2026-09-08。不含最终提交。真机 OnePlus 9R `b0644fb5` / `4aabc387-6e4b-4b59-a525-b1c119ec7f5b`，云端 `https://43.133.243.154.sslip.io`。

## 本轮代码（本地工作区，尚未发到首尔 APK）

- 恢复只接受 `PAUSED_WAITING_USER`；`CANCELLED` / `CANCEL_REQUESTED` / 未 ack 均 409。
- Companion 心跳 409 记 `LEASE_FENCED` 停跑。
- 暂停时把上一完成步写入检查点；恢复不重放已完成步。
- 账号/绑定/Recipe 不一致保持暂停。

本地验证：`tests/integration/test_platform_tasks.py` 10 passed；Companion `ResumeValidatorTest` / `LocalAutomationExecutorTest` / `AutomationStoreTest` gradle 通过。

## 真机主路径（首尔现网 API + 已安装 Companion）

任务 `0c979bfd-5f32-4c37-972e-df7c9b210619`，目标包 Companion 自身：

1. `find-home` 完成（step 0）。
2. `hold-for-operator`（home NOT_EXISTS，长等待）开始后下发暂停。
3. `PAUSED_WAITING_USER`，`pauseAckAt=2026-09-08T03:36:54.792292Z`，`controlMode=REMOTE`。
4. 后继任务 `d2e8fea4-118a-4bd7-8b35-341c1b680f16` 保持 `QUEUED`。
5. `pageVerified=false` → 409。
6. 同 taskId resume：`resumeCount=1`，`controlEpoch=89`，`RESUME_CHECK` 后回到 `RUNNING`。
7. 事件：`STEP_SUCCEEDED 0` → `STEP_STARTED 1` → `PAUSED_WAITING_USER` → `RESUME_CHECK` → 再次 `STEP_STARTED 1`，没有重放 step 0。
8. 取证后取消，状态 `FAILED/CANCELLED`；队头释放后后继任务才执行成功。未点击闲鱼发布。

## 顺手处理的阻塞

旧发布任务 `54548b87-...`（T026 现场）当时卡在 `RESUME_CHECK` 且 command 是 `xianyu.publish_listing.v1`。已 `mark-unknown` 为 `RECONCILING`，避免 Companion 自动续跑发布。对该任务 resume/retry 均为 409。

## 取消不可恢复

见 `cancel.md`：任务 `9c24680d-...` 暂停 ack 后取消，再 resume 409。

## 未完成

- 首尔 APK 仍是旧包，本轮 Kotlin 修复未装上真机。
- 失租立停只在接口单测覆盖（旧 lease 心跳 409），未再做一个单独真机计时。
- P09 断网二次真实提交未做；禁止真实发布/扣费/删除。
