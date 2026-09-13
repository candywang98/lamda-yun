# P09 闲鱼提交前（precommit）输入真机验证 — 2026-09-13

Contract scope: `p09-wiring/20260912.1` Android 侧输入原语（REVIEW F03/F04/F06/F07 的 W1-A 切片）。
本报告**不**主张 P09-XY-G3（真实发布）通过，也不主张表单分类（F08）已解决。

## 基线

- 集成分支 `integration/p14-20260909`，HEAD `802e021`（本切片 4 个提交：7a50034 / 90c43f5 / e8e4ad9 / 802e021）。
- 设备 OnePlus 9R `b0644fb5`，Android 14，已装 APK SHA-256 `db55c57121778c9160a425388572cfc441ebb7ecec7a9a792d379ae8d2b1a950`（`adb install -r` 就地升级，绑定与数据保留）。
- 服务端：首尔 `cloudctl-mobile-api`，release `p09-ledger-ce823ad`，设备绑定 `4aabc387`（tenant `...1111`），任务由 operator API（dev identity headers）创建。

## 本切片修复的两个真实缺陷（均在真机上暴露，单测无法覆盖）

1. **Android 14 IME 设置读取崩溃**（e8e4ad9）：targetSdk 35 下 `Settings.Secure.ENABLED_INPUT_METHODS` 读取抛 `SecurityException`，MainActivity 启动即崩；ColorOS 随即自动关闭 Companion 无障碍。修复为 `InputMethodManager.enabledInputMethodList` 公开 API + `DEFAULT_INPUT_METHOD` 读取保护降级。无障碍由用户手动恢复一次（生产版 adb 无法写 secure 设置；ColorOS 设置页 secure，uiautomator 不可导出）。
2. **描述读回前缀误报**（802e021）：`FlutterTextCommit.accepted()` 的 16 字符前缀兜底把「仅开头相同的旧草稿」判为输入成功。真机任务 c240deb1（本目录 task2-*.json）在表单恢复旧草稿时 fill-description 被跳过并误报 SUCCEEDED。修复为仅接受空白归一化后的完整文本包含，并新增旧草稿回归测试。

## 预提交任务（无发布动作）

复用 2026-09-12 真实任务 37376e69 的冻结内容与已批准定位器：描述「Notion Business 兑换券，图示价值 $240。拍下后按说明发送兑换方式。支持当面交易。」、价格 199、媒体资产 `01a07ace`。步骤 1–17 与原任务一致到 capture-form 截图为止，**删除全部 location/publish 点击步骤**，以 `run.log XIANYU_PREPARE_VERIFIED` 结束。见 task-request.json。

- 任务 a7a37d39（#1）：FAILED / STEP_TIMEOUT @ step 0 —— 创建即被领取，而手机仍停在旧任务遗留的表单页，find-home-sell 不可见。预期内的现场状态问题，无副作用。
- 任务 c240deb1（#2）：SUCCEEDED（23s），但读回发现描述字段是旧草稿文本（「虚拟商品，直接发链接…」），证明缺陷 2。task2-final.json + readback-c240deb1.md。
- 任务 553afa9c（#3，严格读回版本）：SUCCEEDED（62s），屏幕读回命中冻结文本全部特征（发送兑换方式 ✅ / 支持当面交易 ✅ / 旧草稿「虚拟商品」已消失 ✅ / 199 ✅），停在发布前（存草稿可见，无 click-publish）。task3-final.json + readback-553afa9c.md。

## 运行条件

- CloudCtl Input IME：`adb shell ime enable/set` 设为当前输入法（执行后已恢复搜狗）。
- 无障碍：全程开启（除崩溃后的一次人工恢复）。
- 手机蜂窝网络直连首尔 API；Companion 心跳正常（服务器 last_seen 与运行时刻一致）。

## 证据

| 证据 | 位置 | 说明 |
|---|---|---|
| 任务定义 | `task-request.json` | 17 步，无发布动作 |
| #2 误报运行 | `task2-c240deb1-final.json`、`readback-c240deb1.md` | 状态 SUCCEEDED 但读回不符（缺陷证据） |
| #3 验证运行 | `task3-553afa9c-final.json`、`readback-553afa9c.md` | 状态 SUCCEEDED 且读回精确匹配 |
| 表单截图（设备侧） | 未入仓库（含账号内容）；SHA-256：c240deb1=`284228514b2d1e508fd53d6523470f15ad6df7a512ea9d0e9ee78a7d49f313e7`，553afa9c=`6a05bd0da1085f0a4149b46bdd80938520896627e6cccc461ece8fbbbba3cc2b` | 手机 `files/automation-evidence/<taskId>/xianyu_publish_form.png` |
| 服务器事件流 | mobile_task_event，553afa9c 全 17 步 STARTED→SUCCEEDED | 服务器 PostgreSQL |

## 软件门禁

- Android 单测：180 passed / 0 failed / 0 skipped（`testDebugUnitTest`）。
- 后端焦点测试：46 passed / 1 skipped（`test_recipe_package.py` + `test_p09_action_ledger.py`，SQLite 锁用例照旧 skip）。

## 未主张（Not claimed）

- P09-XY-G3：未点击发布，无真实商品身份核验。
- 表单分类（商品 vs 服务）：本验证只证明输入原语；F08 缺口仍在。
- 位置选择、素材身份核验（F09 弱点未改）、公网 Basic Auth 登录、Recipe 引擎 input/wait 真实语义（F01）。
- G2 故障注入（断网/重启）在本切片未重复；引用 wiring-20260912 与 ledger-runtime-20260910 既有证据。
