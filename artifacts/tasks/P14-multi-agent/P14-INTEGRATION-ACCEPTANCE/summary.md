# P14 单机版本生命周期验收 — 2026-09-10

结论：**P14 在授权 OnePlus 9R 单机范围内验收通过**。不代表 G3 真实业务提交门禁、P15 APK 用户侧升级流程或其他业务包通过。

## 版本与环境

- 集成分支 `integration/p14-20260909`；运行逻辑修复 `80a5de9`、`1ca0c1a`；设备存储测试 `033e5ac`、`5eaa2f1`。
- 首尔 API 实际部署 `p14-bb81051`，数据库迁移 `20260909_0015`。本轮后续提交仅改 Android 与测试/报告，后端生产源码未变。
- OnePlus 9R LE2100，Android 14，ADB `b0644fb5`，设备 `4aabc387-6e4b-4b59-a525-b1c119ec7f5b`。
- APK 覆盖安装保留绑定与任务库；使用原已安装调试签名，证书 SHA-256 `667ebabbd69327228215c090fbacee58881d5392c83cfc41cf3fb82f2abb4736`。Recipe Ed25519 校验始终开启。
- 网页验收通过经 SSH 认证的本机隧道连接真实首尔 API，关闭 mock；同源码构建只改变 API 地址。**未声称通过公网 Nginx Basic Auth 登录验收**。

## 验收矩阵

| 条件 | 实际证据 | 结果 |
|---|---|---|
| 网页人工登记、发布、回退 | 浏览器确认发布 1.0.2、回退 1.0.1，并登记/发布签名 1.0.3；真实 API 审计与设备 SQLite/WAL 活动目录一致 | 通过 |
| 签名版本领取与执行 | 历史任务 `c1762158…` 固定 1.0.2；`74bf9edc…` 固定回退后的 1.0.1；本轮最终任务 `c8ec815c…` 再次固定 1.0.1 并成功 | 通过 |
| 运行任务固定原版 | `caa22da3…` 领取 1.0.3 后，运行期间发布 1.0.2，任务 pin 不变 | 通过 |
| 暂停任务固定原版 | 同任务 PAUSED_WAITING_USER；设备 active 仍是 1.0.3，pending 是 1.0.2 | 通过 |
| 重启与同任务恢复 | 保留数据安装修复 APK 后，同 taskId 恢复 RUNNING，resumeCount=2，仍用 1.0.3；只重新进入 hold，未重放 started | 通过 |
| 下载中断保留旧版 | 对唯一 1.0.4 版本路径实施真实 HTTPS 响应截断：685 字节只发送 32 字节；手机报 Cloud response was truncated，active 仍为 1.0.1，pending=null | 通过 |
| 中断后自动恢复 | 恢复正常路径后，手机自动下载、验签、激活 1.0.4；最后明确回退到 1.0.1 | 通过 |
| 文件与持久状态恢复 | OnePlus instrumentation：IOException、截断签名 JSON、孤立临时文件三项；真实文件系统/SQLite 重新打开后旧包仍可验签读取 | 3/3 通过 |
| 每设备版本审计 | recipe.version.published / rolled_back / task.pinned，含 actor、时间、版本和设备信息 | 通过 |

暂停任务是控制等待验收，取证后主动取消，最终 FAILED/CANCELLED，**没有把它记录为发布或任务成功**。最终稳定性探针 `c8ec815c-bbf6-4368-94c2-822b80e37df2` 为 TERMINAL_CONFIRMED/SUCCEEDED。

## 本轮发现并修复

1. Recipe `wait` 之前只写日志。现在等待允许的定位器达到可见/启用状态，受整包截止时间约束；协程取消及暂停、取消、失租控制能中断等待，控制失败不能经 onFailure 转成成功。
2. 恢复检查此前要求等待目标已经可见，导致合法的待条件等待不能恢复。现在等待分支仍核验 pageVerified、账号、绑定、签名版本、目标应用和允许定位器，由执行器继续等待目标出现；点击等其他动作仍要求目标可见。
3. instrumentation 的测试 APK 私有缓存不能由目标 UID 使用。改为唯一临时缓存子目录，ContextWrapper 强制数据库落入该目录并核对路径，不打开或删除业务数据库。

## 验证命令与结果

- 后端 8 个相关测试文件：`pytest -q tests/integration/test_p14_recipe_versions.py tests/integration/test_backend_control_api.py tests/integration/test_mobile_task_api.py tests/integration/test_control_api_migrations.py tests/integration/test_platform_tasks.py tests/unit/test_command_factory.py tests/unit/test_command_v1.py tests/unit/test_recipe_package.py`：**86 passed**。
- Web `pnpm --filter @cloudctl/web test`：**139 passed / 28 files**；typecheck 通过。同源码真实 API 地址构建成功，保留既有大 chunk 提示。
- Android `testDebugUnitTest --tests '*RecipeEngineTest' --tests '*RecipeResumeProgressTest' --tests '*RecipeLifecycleTest' --tests '*AutomationStoreTest' --tests '*ResumeValidatorTest' assembleDebug`：**62 tests，0 failures/errors/skips，BUILD SUCCESSFUL**。
- `assembleDebugAndroidTest` 成功；`adb -s b0644fb5 shell am instrument -w -r -e class com.company.cloudctl.companion.updates.RecipeStorageInstrumentationTest com.company.cloudctl.companion.test/androidx.test.runner.AndroidJUnitRunner`：**OK (3 tests)**。

## 收尾和限制

- 临时截断服务与恢复定时器已停止。Nginx 原片段 SHA-256 前后一致：`ffeba456d36730fba8d492bc4b592f761d50eb6abd900a95fc7133fe77da34b6`；API 与 Nginx active、health ok。
- instrumentation 后系统将无障碍服务标为故障，恢复探针 `19cd79ed…` 因 ACCESSIBILITY_NOT_ENABLED 失败。系统拒绝 ADB 直接改 secure settings，Root 通过正常系统设置重新启用原服务，Crashed services 清空，最终探针成功。历史失败未改写。
- 最终设备 active=1.0.1，pending=null；无本轮遗留运行/暂停任务。
- 本轮未执行任何闲鱼/小红书真实发布、删除、扣费；G3 仍未验收。
- 原始证据保存在本地 `runtime-20260910/`，包含设备 SQLite/WAL、任务 JSON、审计与截断日志。原始数据库不纳入 Git。

## 接续

P14 的依赖可解锁；P08 已补齐 CommandV1 同任务跨版本恢复证据，但其他 G2 故障场景需按计划单独核对。下一步核对 P09/G3 的真实故障验收要求，并按 READY 规则安排 P15 与其他独立模块，不能把本报告扩大为其他包验收通过。
