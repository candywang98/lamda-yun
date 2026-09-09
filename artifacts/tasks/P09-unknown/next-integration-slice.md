# P09 下一接线切片：已确认缺口与实施边界

2026-09-10；当前先执行 `p09-reconcile/20260910.1` 双路加固。此文档不是 G3 通过证明，也不开放真实副作用。

## 已核对的代码事实

1. `IrreversibleActionGate` / `IrreversibleActionCoordinator` 存在，但 `CompanionSyncService`、`RecipeEngine` 没有调用它们。现有 gate/coordinator 测试只调用独立类。
2. Python `RecipeGraph` 已有 `commitActionId`，`RecipeState` 已有 `postcondition`；Android `RecipePackage` / `RecipeState` 尚未解析这些字段。已有测试 fixture 把 commitActionId 指向 checkpoint，不等于真实提交能力。
3. `CommitIntentRow` 外键指向 `publish_target`，现有 create_commit_intent 要求 PublishTarget、当前租约、fencing token、提交前证据；不可直接拿 mobile task UUID 充当 target ID。
4. `PlatformTaskCreate.publishTargetId` 是可选字段，当前 create 仅存入 commandPayload。任务领取固定签名版本不等于提交授权或提交结果证据。
5. 服务器 event/finish 与本地 UNKNOWN 退出保护存在缺口，已分别派发 CONTROL 和 ANDROID 修复。合并通过前不接真实点击。

## 下一切片需要冻结的内容

- 显式提交状态：只处理签名 graph.commitActionId 指定的状态。声明必须指向存在状态；生产提交状态必须有允许的动作定位器和明确结果定位器。普通 log/checkpoint 不得冒充业务提交成功。
- 动作身份：绑定原 taskId、固定 Recipe ID/hash、commitActionId；参数 hash 包含 commandType、accountId、bindingVersion、snapshotSha256、targetPackage 和规范化 parameters，排除可变 lease/attempt 时间字段。
- 提交前：检查当前控制请求、有效租约/epoch、账号绑定、任务冻结参数及明确授权；确认结果定位器未预先出现。先持久化 intent，再执行一次动作。
- 提交后：动作 API 返回只代表点击调用完成；只有独立结果读回才能标 APPLIED。断网、丢 ACK、取消、超时、进程退出及结果不唯一均保留 UNKNOWN/RECONCILING，不走普通 resume/retry。
- 双端核对：服务端人工/自动核对有唯一证据后，必须有明确设备侧结果同步，才能解除本地 UNKNOWN。当前只有服务器 reconcile 不能据此删除或伪造本地 journal。
- 非发布类操作不能伪造 PublishTarget 外键；应复用现有操作领域或明确新增任务动作账本契约后，再由单一迁移 owner 实施。

## 先做的无业务副作用验证

使用独立 instrumentation 测试数据，在 OnePlus 上让真实 gate/coordinator 包裹一个可读回的本地计数动作，核对 SQLite 重开、INTENT/UNKNOWN/APPLIED、重复 actionKey 与参数变化、取消/丢确认和队头阻塞。它能证明门禁行为，不能替代每类真实平台动作的 G3 验收。

## 真实 G3 验收仍需的输入

每类发布、扣费、删除都需要确定的测试账号、目标对象、冻结参数和可核对的结果。当前用户授权足够执行开发/部署/ADB，但仓库没有提供本轮要发布的商品内容、可扣费预算或可删除对象。先完成全部可独立开发与无副作用验证；在需要真实副作用前准备具体可审阅的最小测试对象，再向用户确认缺失的业务输入，不以笼统授权推断任意真实对象可被修改。
