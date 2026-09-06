# 手机本地自动化：无 Edge / 无 USB 验收路径

日期：2026-09-01

范围仅限 Web 工作台 `/mobile-automation`、Control API `/api/v1/mobile/*` 和 Companion `/companion/v2/*` 闭环。

## 合同结论

- Web 只调用 Control API：`POST /api/v1/mobile/enrollments`、`GET/POST /api/v1/mobile/tasks`、`GET /api/v1/mobile/tasks/{id}`。
- APK 主动出站调用 `/companion/v2/enroll`、`/tasks/claim`、heartbeat、events、complete/fail。
- Web 不导入 Mock client，不连接手机私网端口，不调用 Edge API，也不使用 USB/ADB 投递任务。
- Web 只生成七种允许动作：`ui.find`、`ui.tap`、`ui.input`、`ui.wait`、`ui.screenshot`、`ui.assert`、`run.log`。
- Web 已把 locator 收紧为 APK 当前实际接受的共同子集：`^[a-z][a-z0-9_]{0,79}$`；input 固定 `replace=true` 且最多 1024 字符。

## 最终验收步骤

1. 在 Control API 中准备一台租户内设备记录，启动 Web 和 Control API。
2. 电脑断开手机 USB，确认 `adb devices` 不包含目标手机；停止所有 Edge Gateway 进程。
3. 在 `/mobile-automation` 选择设备，创建 10 分钟一次性入网码。
4. 手机仅通过公网/Wi-Fi/蜂窝网络访问 Control API，在 Companion 输入入网码完成绑定。
5. Web 创建只含允许列表动作的任务，确认状态为 `QUEUED`。
6. APK 主动 claim，状态依次进入 `CLAIMED`/`RUNNING`，逐序上报事件，最后进入 `SUCCEEDED` 或明确 `FAILED`。
7. Web 详情显示真实 step event、结果和错误；全程不恢复 USB，不启动 Edge。
8. Control API 短时断网再恢复，确认 APK 能继续 heartbeat/事件补传且任务不重复执行。

## 当前实现状态与剩余阻断

此前两项合同阻断已经解除：

- `run.log` 的服务端 envelope 与 Android 严格 parser 已使用相同字段集合。
- Alembic `20260901_0007` 已允许手机直连设备使用 `edge_id = NULL`；mobile enrollment
  会创建该类型设备。

截至 2026-09-01，最终验收仍未通过的唯一硬阻断是真机条件：OnePlus 的 USB 调试授权尚未完成，
因此两个测试 APK 还没有被确认安装到目标机，也尚未完成“停 Edge、停 ADB、拔 USB后从公网工作台
下发并回传”的实机闭环。ADB 只允许用于首次安装和调试，不可作为验收执行链路。

验收证据必须同时包含：目标手机设备身份、APK 版本、任务 ID、手机本地 journal、Control API
有序事件与终态，以及执行阶段电脑端 Edge/ADB 已停止且 USB 已断开的记录。缺少任一项都不得宣称
无 USB 生产验收完成。

自动化回归：`apps/web/tests/mobile-automation-view.spec.ts` 验证 UI 合同，`mobile-automation-boundary.spec.ts` 验证页面不引入 Mock、Edge、USB/ADB 客户端或任意执行动作。
