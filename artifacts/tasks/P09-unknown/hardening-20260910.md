# P09 不确定状态加固 — 2026-09-10

本轮完成并部署的是 **P09 状态保护与本地防重切片**。**P09 整包/G3 尚未验收通过**：真实 Recipe 提交入口、提交前云端记账及双端核对解锁仍需接线；未操作真实发布、扣费或删除。

## 已实现

- 后端 `21202a5`：RECONCILING 不能经普通设备状态事件、finish、pause、cancel、retry、ack-paused 退出；普通日志/步骤事件保留状态，重复事件与租约检查保留；终态不能被重新打开；明确 reconcile 才能处理核对结果。
- 统一完成回执 completedAt 的 UTC 表达，修复 SQLite 重放时同一时刻有/无时区后缀不一致。
- Android `ef9eb2b`：默认没有结果确认就保持 UNKNOWN；INTENT/UNKNOWN 在 SQLite 重新打开后保留 RECONCILING，阻止领新任务、普通恢复、替换租约、finish 和版本激活绕过；取消发生在 intent 之后则记 UNKNOWN 并重新抛出 CancellationException。
- APPLIED 重复调用不再执行回调；身份/参数 hash 变化拒绝。未把这些类直接接到第三方业务点击上。

## 验证

- 后端新 P09 用例及 platform/mobile/P14/control API 回归：**89 passed in 26.92s**。确认导入的是独立 p09-control worktree 源码。
- Android gate/coordinator/store/lifecycle/engine/resume：**78 tests，0 failures/errors/skips，BUILD SUCCESSFUL**。
- Root 补充 `IrreversibleActionInstrumentationTest`，在 OnePlus 真实 SQLite/独立缓存目录中用可读回的本地计数验证：丢确认不重做、APPLIED 重复不重做、取消并重启后 UNKNOWN 不重做，**OK (3 tests)**。这不是平台业务副作用验收。
- 首尔已部署 `releases/p09-ef9eb2b`；health ok。部署的 mobile_service.py 与 platform_tasks.py 哈希分别与本地完全一致：`5b360afeb82fadec22238bd11a2ab0060919341340effc2c212db7c019306ecc`、`5d9b9d52e878df72b4946a10c8c413ee5135a773b0773b65e2dd588bc3b5c2af`。
- 保留原 `p14-bb81051` 服务目录和配置。新配置为 `99-p09-hardening.conf`，无数据库迁移。
- Android 使用原设备签名覆盖安装，保留绑定/任务库；部署前实际 action_journal 为空，无历史 UNKNOWN 被误处理。
- instrumentation 后通过正常系统设置恢复原无障碍服务，Crashed services 为空。整链路探针 `5897215f-5e57-4bd8-9f1d-a33aaef47c1f` **SUCCEEDED**。

## 证据

本地 `runtime-20260910/` 保存 backend/Android 日志、设备测试结果与部署探针结果。原始日志和数据库不纳入 Git。Root authored instrumentation 源码纳入 Git。

## 下一步

见 `next-integration-slice.md`：冻结最小提交入口契约，处理云端 intent 与本地 once gate 的顺序、明确后置结果、断网/丢 ACK 及 server reconcile 到本地 journal 的可信同步。不要把独立 gate 测试或本地计数测试记作真实平台 G3 通过。
