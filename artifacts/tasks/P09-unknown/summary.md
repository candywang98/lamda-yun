# P09 不确定结果停止（无真实发布）

## 契约

- 二次 `recordActionIntent` 在未 APPLIED 时返回 `UNKNOWN`，不得再点。
- 已 APPLIED 的 actionKey 再次 INTENT 仍返回 `APPLIED`，不重做。
- `commitIntent` 暂停 ack 后进入 `RECONCILING`，resume/retry 409。
- 已成功任务不能 `ack-paused` / `mark-unknown`。

本地：`test_platform_tasks.py` 12 passed；`AutomationStoreTest` 含 UNKNOWN/APPLIED。

## 现网

闲鱼发布任务 `54548b87-...` 保持核对/失败，resume 409，retry 409。未做断网二次真实提交。
