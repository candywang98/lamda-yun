# C8 API 34 隔离输入靶场真机尝试

- 时间：2026-09-23（Asia/Shanghai）
- 设备：OnePlus 9R，USB serial `b0644fb5`，Android 14 / API 34。
- 结论：**未执行 instrumentation，真机输入结果未产生**。Grok 4.7 子代理在模型请求阶段连续两次被 provider 拒绝；按同一阻塞点两次后禁止第三次原样重试的规则停止。
- 边界：不能标记为 API 34 输入通过，更不能代表闲鱼 Flutter/ColorOS 聊天或描述字段验收；API 29–32 仍未真机验收。

## 准入与隔离

- 首尔权威生产库于 2026-09-22 23:45:29 Asia/Shanghai 以只读事务重查：目标设备 REGISTERED 且心跳新鲜；活动 lease=0、CLAIMED/RUNNING task=0、preview=0、active debug session=0。
- USB `b0644fb5` 与 Wi-Fi `192.168.5.6:5555` 的 serial、型号、产品名、API 与 Android ID 一致；本轮只使用 USB。
- 本机未发现活跃 scrcpy、Appium、uiautomator instrumentation 或其他 ADB 安装/驱动进程。
- 主会话取得本地 `DEVICE:b0644fb5` 锁，fencing=2；owner token 仅存 mode 0600 临时文件，未交给 Grok，收尾后已删除。
- 安装并验证的独立包：`com.company.cloudctl.inputharness`、`com.company.cloudctl.companion.debug`、`com.company.cloudctl.companion.debug.test`。生产 `com.company.cloudctl.companion` 未替换。
- ColorOS 的每个安装确认与 debug 无障碍授权均通过系统正常界面完成；没有修改 secure settings、没有 root、没有绕过用户授权。
- debug 包安装后仅有 `CloudCtlAccessibilityService`；无生产网络权限、同步服务、BootReceiver、MediaProjectionService、MainActivity 或 CloudCtlInputMethod；debug 私有目录无生产 binding。
- 安装后再次只读检查生产：active lease=0、running task=0。

## Grok 4.7 执行结果

计划的唯一命令为：

`adb -s b0644fb5 shell am instrument -w -r -e class com.company.cloudctl.companion.automation.DiagnosticInputDeviceTest com.company.cloudctl.companion.debug.test/androidx.test.runner.AndroidJUnitRunner`

该命令没有被执行：

1. 第一次 Grok 4.7 派发在模型请求阶段收到 `Provider rejected the model request`。
2. 确认无 instrumentation 进程、字段未写、搜狗不变后，第二次精简派发仍在模型请求阶段收到相同拒绝。
3. 未进行第三次原样派发，主会话也没有替代 Grok 运行命令。

因此没有 `DIAG_INPUT` proof 行，也没有 `INPUT_VERIFIED`、commitCount、generation、field hash 或 node key hash 可验收。

## 无副作用与恢复

- 两次 provider 拒绝后无 instrumentation 进程。
- 隔离 harness 编辑器仍为空；UI Automator 只见初始 hint `isolated field`，未出现固定 fixture `你好🙂\n第二行`。
- 默认输入法始终为 `com.sohu.inputmethod.sogouoem/.SogouIME`。
- 最终生产复核：active lease=0、running task=0、preview=0、active debug session=0。
- 通过系统界面关闭 `CloudCtl debug input` 无障碍服务。
- 卸载本轮安装的三个测试包；生产 Companion 仍在原路径，既有生产无障碍服务与 AirDroid 服务保留。
- 本地设备锁已释放为 FREE；owner token 临时文件已删除。
- 未打开闲鱼业务页面，未发送聊天、发布商品、提交评价、删除、收费或推广。

## 下一检查点

恢复可用的 Grok 4.7 provider 后，从生产只读占用重检、精确设备锁、APK 哈希复核和系统授权开始重新准入；不得复用本次已释放的锁或把本次安装/授权过程当作输入验收。
